import asyncio
import aiohttp
import ssl
import base64
import logging
import json
import ftplib
import tempfile
import secrets
import subprocess
import os
import datetime
from app.core.config import settings

# Imports for cryptography
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


class SonicWallValidator:
    def __init__(self, firewall_settings):
        self.firewall_settings = firewall_settings
        self.base_url = f"https://{self.firewall_settings.public_ip}:{self.firewall_settings.port}/api/sonicos"  # noqa: E501

        username = self.firewall_settings.admin_username
        password = self.firewall_settings.api_key
        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()

        self.headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self.test_files_created = []
        self.current_test_cert_name = None

    def _generate_sonicwall_friendly_cert_name(self) -> str:
        """Generate SonicWall-friendly certificate name."""
        timestamp = datetime.datetime.now().strftime("%m%d%H%M")
        unique_id = secrets.token_hex(3)
        cert_name = f"TestCert_{timestamp}_{unique_id}"
        logger.info(f"   Generated SonicWall-friendly cert name: {cert_name}")
        return cert_name

    async def _make_request(
        self, session, method: str, endpoint: str, data=None, timeout: int = 30
    ):
        """Make API request and return (status, response_data)."""
        url = f"{self.base_url}{endpoint}"
        headers = self.headers.copy()

        if isinstance(data, str) and endpoint == "/direct/cli":
            headers["Content-Type"] = "text/plain"
        elif isinstance(data, dict) or isinstance(data, list):
            headers["Content-Type"] = "application/json"

        try:
            if method.upper() == "POST":
                if headers["Content-Type"] == "text/plain":
                    response_obj = await session.post(
                        url, headers=headers, data=data, timeout=timeout
                    )
                else:
                    response_obj = await session.post(
                        url, headers=headers, json=data, timeout=timeout
                    )
            elif method.upper() == "GET":
                response_obj = await session.get(url, headers=headers, timeout=timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            async with response_obj as response:
                status = response.status
                raw_text = await response.text()

                try:
                    if (
                        raw_text.strip().startswith(("{", "["))
                        and "application/json"
                        in response.headers.get("Content-Type", "").lower()
                    ):
                        result_json = json.loads(raw_text)
                        return status, result_json
                    else:
                        return status, {"raw_response": raw_text}
                except json.JSONDecodeError:
                    return status, {"raw_response": raw_text}

        except Exception as e:
            logger.error(f"Request to {url} failed: {e}")
            return None, {"error": str(e)}

    async def authenticate(self, session) -> bool:
        """Authenticate to SonicWall API."""
        auth_data = {"override": True}
        status, response = await self._make_request(
            session, "POST", "/auth", data=auth_data
        )

        if status not in [200, 201, 204]:
            logger.error(f"Authentication failed: HTTP {status} - {response}")
            return False

        return True

    async def logout(self, session):
        """Logout from SonicWall API."""
        try:
            await self._make_request(session, "POST", "/auth/logout")
        except Exception as e:
            logger.warning(f"Error during logout: {e}")

    async def check_certificate_exists(
        self, session, cert_name: str, context: str = ""
    ) -> bool:
        """Check if certificate exists on SonicWall."""
        cli_command = f"show certificate name {cert_name} status\nexit"
        status, response_data = await self._make_request(
            session, "POST", "/direct/cli", data=cli_command
        )

        if status is None:
            return False

        if (
            status == 200
            and isinstance(response_data, dict)
            and "certificate" in response_data
        ):
            if response_data.get("certificate") == cert_name:
                return True

        if isinstance(response_data, dict) and "status" in response_data:
            status_info = response_data.get("status", {})
            if isinstance(status_info, dict):
                info_list = status_info.get("info", [])

                for item in info_list:
                    message = item.get("message", "").lower()
                    if item.get("level") == "error" and (
                        "no certificate found for this name" in message
                        or "not a reasonable value" in message
                    ):
                        return False

        return False

    def _generate_test_certificate(self, common_name: str) -> tuple[str, str]:
        """Generate a unique test certificate and key."""
        key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048, backend=default_backend()
        )
        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "NE"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "Omaha"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Secur-Serv"),
                x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            ]
        )
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(
                datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(days=1)
            )
            .not_valid_after(
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(days=365)
            )
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None), critical=True
            )
            .sign(key, hashes.SHA256(), default_backend())
        )
        cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
        key_pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode("utf-8")
        return cert_pem, key_pem

    def _create_pfx(self, cert_pem: str, key_pem: str, password: str) -> bytes:
        """Create PFX file using OpenSSL."""
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".crt"
        ) as cert_file, tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".key"
        ) as key_file, tempfile.NamedTemporaryFile(
            delete=False, suffix=".pfx"
        ) as pfx_file:
            cert_file.write(cert_pem)
            key_file.write(key_pem)
            cert_file_path = cert_file.name
            key_file_path = key_file.name
            pfx_file_path = pfx_file.name

        try:
            cmd = [
                "openssl",
                "pkcs12",
                "-export",
                "-out",
                pfx_file_path,
                "-inkey",
                key_file_path,
                "-in",
                cert_file_path,
                "-password",
                f"pass:{password}",
            ]
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            with open(pfx_file_path, "rb") as f:
                pfx_data = f.read()
            return pfx_data
        finally:
            for path in [cert_file_path, key_file_path, pfx_file_path]:
                if os.path.exists(path):
                    os.unlink(path)

    async def upload_certificate_to_ftp(self, cert_name: str):
        """Upload test certificate to FTP server."""
        cert_cn_suffix = secrets.token_hex(4)
        cert_common_name = f"cert.test{cert_cn_suffix}.local"
        cert_pem, key_pem = self._generate_test_certificate(cert_common_name)

        pfx_password = "TestPassword123"
        pfx_data = self._create_pfx(cert_pem, key_pem, pfx_password)

        filename = f"{cert_name}_{secrets.token_hex(4)}.pfx"

        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(pfx_data)
            temp_file_path = temp_file.name

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._ftp_upload, temp_file_path, filename)

            self.test_files_created.append(filename)
            ftp_url = "ftp://{user}:{pwd}@{host}/{file}".format(
                user=settings.FTP_USER,
                pwd=settings.FTP_PASS,
                host=settings.FTP_HOST,
                file=filename,
            )

            return ftp_url, pfx_password
        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    def _ftp_upload(self, local_path, remote_filename):
        with ftplib.FTP() as ftp:
            ftp.connect(settings.FTP_HOST, settings.FTP_PORT)
            ftp.login(settings.FTP_USER, settings.FTP_PASS)
            with open(local_path, "rb") as f:
                ftp.storbinary(f"STOR {remote_filename}", f)

    async def import_certificate(
        self, session, cert_name: str, ftp_url: str, pfx_password: str
    ) -> bool:
        """Import certificate using Direct CLI."""
        cli_commands = f"certificates\nimport cert-key-pair {cert_name} password {pfx_password} ftp {ftp_url}\ncommit\nend\nexit"  # noqa: E501
        status, response = await self._make_request(
            session, "POST", "/direct/cli", data=cli_commands
        )

        if status in [200, 201, 204]:
            if isinstance(response, dict) and "status" in response:
                status_info = response.get("status", {})
                if isinstance(status_info, dict):
                    info_list = status_info.get("info", [])

                    for info in info_list:
                        if info.get("level") == "error":
                            logger.error(
                                "   ❌ Import command reported error: {}".format(  # noqa: E501
                                    info.get("message", "Unknown error")
                                )
                            )
                            return False

                    if status_info.get("success") is True:
                        for info in info_list:
                            if (
                                "successfully loaded certificate and key pair"
                                in info.get("message", "").lower()
                            ):
                                return True

                    # Fallback for ambiguous success cases like "No changes made."
                    return True

            return True
        else:
            logger.error(f"   ❌ Import command failed: HTTP {status} - {response}")
            return False

    async def delete_certificate(self, session, cert_name: str) -> bool:
        """Delete certificate using Direct CLI."""
        delete_commands = (
            f'certificates\nno certificate "{cert_name}"\ncommit\nend\nexit'
        )
        status, response = await self._make_request(
            session, "POST", "/direct/cli", data=delete_commands
        )

        if status in [200, 201, 204]:
            if isinstance(response, dict) and "status" in response:
                status_info = response.get("status", {})
                if isinstance(status_info, dict):
                    info_list = status_info.get("info", [])
                    for info in info_list:
                        if info.get("level") == "error":
                            if (
                                "not found" in info.get("message", "").lower()
                                or "does not exist" in info.get("message", "").lower()
                            ):
                                return (
                                    True  # Cert is already gone, so this is a success.
                                )
                            return False
                        if (
                            "certificate has been successfully deleted"
                            in info.get("message", "").lower()
                        ):
                            return True
            return True
        else:
            return False

    async def cleanup_ftp_files(self):
        """Clean up FTP test files."""
        if not self.test_files_created:
            return
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._ftp_cleanup)
        except Exception as e:
            logger.error(f"FTP cleanup connection error: {e}")

    def _ftp_cleanup(self):
        with ftplib.FTP() as ftp:
            ftp.connect(settings.FTP_HOST, settings.FTP_PORT)
            ftp.login(settings.FTP_USER, settings.FTP_PASS)
            for filename in self.test_files_created:
                try:
                    ftp.delete(filename)
                except Exception:
                    pass

    async def run_complete_test(self):
        """Run complete certificate import and delete test."""
        self.current_test_cert_name = self._generate_sonicwall_friendly_cert_name()
        yield "🚀 SonicWall Certificate Manager Test"
        yield f"Certificate Name: {self.current_test_cert_name}"

        # Use a single aiohttp session for all requests
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=ssl_context)
        ) as session:
            try:
                yield "Authenticating to SonicWall..."
                if not await self.authenticate(session):
                    yield "❌ Authentication failed, aborting."
                    return
                yield "✅ Authentication successful."

                yield "Checking initial certificate status..."
                if await self.check_certificate_exists(
                    session, self.current_test_cert_name, "initial_check"
                ):
                    yield "Certificate already exists, attempting deletion..."
                    await self.delete_certificate(session, self.current_test_cert_name)
                    yield "Waiting for deletion to process..."
                    await asyncio.sleep(5)
                    if await self.check_certificate_exists(
                        session, self.current_test_cert_name, "expecting_absent"
                    ):
                        yield "❌ Failed to delete existing certificate. Aborting."
                        return
                    yield "✅ Pre-existing certificate deleted."
                else:
                    yield "✅ Certificate does not exist, proceeding."

                yield "Creating and uploading test certificate..."
                ftp_url, pfx_password = await self.upload_certificate_to_ftp(
                    self.current_test_cert_name
                )
                if not ftp_url:
                    yield "❌ Failed to upload certificate to FTP. Aborting."
                    return
                yield f"✅ Certificate uploaded via FTP: {ftp_url}"

                yield f"Importing certificate '{self.current_test_cert_name}'..."
                if not await self.import_certificate(
                    session, self.current_test_cert_name, ftp_url, pfx_password
                ):
                    yield "❌ Certificate import failed. Aborting."
                    return
                yield "✅ Certificate import command sent."

                yield "Waiting for import to process..."
                await asyncio.sleep(10)

                yield "Verifying certificate import..."
                if not await self.check_certificate_exists(
                    session, self.current_test_cert_name
                ):
                    yield "❌ Certificate import verification failed. Aborting."
                    return
                yield "✅ Certificate import verified."

                yield "Deleting certificate..."
                await self.delete_certificate(session, self.current_test_cert_name)
                yield "Waiting for deletion to process..."
                await asyncio.sleep(5)

                yield "Verifying certificate deletion..."
                if not await self.check_certificate_exists(
                    session, self.current_test_cert_name, "expecting_absent"
                ):
                    yield "✅ Certificate deletion verified."
                else:
                    yield "❌ Certificate deletion verification failed."
                    return

                yield "🎉 SUCCESS: Complete certificate workflow validated!"
            except Exception as e:
                yield f"❌ Unexpected error during validation: {e}"
            finally:
                yield "Logging out..."
                await self.logout(session)
                yield "Cleaning up FTP files..."
                await self.cleanup_ftp_files()
                yield "Cleanup complete."
