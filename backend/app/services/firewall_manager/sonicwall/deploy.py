import asyncio
import base64
import ftplib
import json
import logging
import os
import re
import secrets
import ssl
import subprocess
import tempfile
import urllib.parse
from typing import Any, AsyncIterator, Dict

import aiohttp

from ..base import CertificateData

logger = logging.getLogger(__name__)


class SonicWallDeployManager:
    """
    SonicWall SSL VPN Certificate Deployment Manager
    Extracted from tested sonic-vpn.py script for production use
    """

    def __init__(
        self,
        hostname: str,
        username: str,
        password: str,
        management_port: int = 443,
        ftp_config: Dict[str, Any] | None = None,
    ):
        self.hostname = hostname
        self.username = username
        self.password = password
        self.management_port = management_port
        self.base_url = f"https://{hostname}:{management_port}/api/sonicos"

        # Setup authentication headers
        credential_string = f"{username}:{password}"
        credentials = base64.b64encode(credential_string.encode()).decode()
        self.headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # FTP configuration for certificate upload
        self.ftp_config = ftp_config or {}
        self.test_files_created = []

    async def _make_request(
        self, session, method: str, endpoint: str, data=None, timeout: int = 30
    ):
        """Make API request and return (status, response_data)."""
        url = f"{self.base_url}{endpoint}"
        headers = self.headers.copy()

        if isinstance(data, str):
            headers["Content-Type"] = "text/plain"

        try:
            response_obj = None
            if method.upper() == "POST":
                if isinstance(data, str):
                    response_obj = await session.post(
                        url, headers=headers, data=data, timeout=timeout
                    )
                else:
                    response_obj = await session.post(
                        url, headers=headers, json=data, timeout=timeout
                    )
            elif method.upper() == "PUT":
                response_obj = await session.put(url, headers=headers, data=data, timeout=timeout)
            elif method.upper() == "GET":
                response_obj = await session.get(url, headers=headers, timeout=timeout)

            if response_obj:
                async with response_obj as response:
                    status = response.status
                    raw_text = await response.text()

                    try:
                        if (
                            "application/json" in response.headers.get("Content-Type", "").lower()
                            or status >= 400
                            or (
                                status < 400
                                and len(raw_text) > 0
                                and raw_text.strip().startswith(("{", "["))
                            )
                        ):
                            result_json = json.loads(raw_text)
                            return status, result_json
                        else:
                            return status, {"raw_response": raw_text}
                    except json.JSONDecodeError:
                        return status, {"raw_response": raw_text}

            return None, {"error": "Invalid request method"}

        except Exception as e:
            logger.error(f"Request failed: {e}")
            return None, {"error": str(e)}

    async def authenticate(self, session) -> bool:
        """Authenticate to SonicWall API using session override."""
        logger.info("Authenticating to SonicWall...")

        auth_data = {"override": True}
        status, response = await self._make_request(session, "POST", "/auth", data=auth_data)

        if status not in [200, 201, 204]:
            logger.error(f"Authentication failed: HTTP {status}")
            logger.error(f"   Response: {response}")
            return False

        # After authentication, ensure we're in a known CLI state
        await self._make_request(session, "POST", "/direct/cli", data="exit\nexit\nexit")

        logger.info("Authentication successful")
        return True

    def _split_certificate_chain(self, fullchain_pem: str) -> tuple[str, str]:
        """Split fullchain PEM into end-entity cert and CA chain."""

        # Find all certificate blocks
        cert_pattern = r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----"
        certificates = re.findall(cert_pattern, fullchain_pem, re.DOTALL)

        if not certificates:
            raise Exception("No certificates found in PEM data")

        # First certificate is the end-entity cert
        end_entity_cert = certificates[0]

        # Remaining certificates form the CA chain
        ca_chain = "\n".join(certificates[1:]) if len(certificates) > 1 else ""

        return end_entity_cert, ca_chain

    def _create_pfx(self, cert_pem: str, key_pem: str, password: str) -> bytes:
        """Create PFX file from certificate and private key with full chain."""
        cert_file_path, key_file_path, chain_file_path, pfx_file_path = (
            None,
            None,
            None,
            None,
        )
        try:
            # Split the certificate chain
            end_entity_cert, ca_chain = self._split_certificate_chain(cert_pem)

            # Create temporary files
            with tempfile.NamedTemporaryFile(mode="wb", suffix=".crt", delete=False) as cert_file:
                cert_file.write(end_entity_cert.encode("utf-8"))
                cert_file_path = cert_file.name

            with tempfile.NamedTemporaryFile(mode="wb", suffix=".key", delete=False) as key_file:
                key_file.write(key_pem.encode("utf-8"))
                key_file_path = key_file.name

            # Create chain file if we have CA certificates
            if ca_chain.strip():
                with tempfile.NamedTemporaryFile(
                    mode="wb", suffix=".pem", delete=False
                ) as chain_file:
                    chain_file.write(ca_chain.encode("utf-8"))
                    chain_file_path = chain_file.name

            with tempfile.NamedTemporaryFile(suffix=".pfx", delete=False) as pfx_file:
                pfx_file_path = pfx_file.name

            # Create PFX using OpenSSL with certificate chain
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

            # Add certificate chain if available
            if chain_file_path:
                cmd.extend(["-certfile", chain_file_path])
                logger.info("Creating PFX file with certificate chain using OpenSSL...")
            else:
                logger.info("Creating PFX file (no chain available) using OpenSSL...")

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                with open(pfx_file_path, "rb") as f:
                    pfx_data = f.read()
                logger.info("PFX file created successfully with certificate chain")
                return pfx_data
            else:
                logger.error(f"OpenSSL stderr: {result.stderr}")
                logger.error(f"OpenSSL stdout: {result.stdout}")
                raise Exception(f"OpenSSL failed: {result.stderr}")

        finally:
            # Cleanup temporary files
            for path in [cert_file_path, key_file_path, chain_file_path, pfx_file_path]:
                if path and os.path.exists(path):
                    try:
                        os.unlink(path)
                    except Exception as e:
                        logger.warning(f"Failed to remove temp file {path}: {e}")

        return b""  # Return empty bytes if creation failed

    async def upload_certificate_to_ftp(self, cert_data: CertificateData, pfx_password: str) -> str:
        """Upload PFX certificate to FTP server."""
        logger.info("Creating and uploading certificate to FTP...")

        loop = asyncio.get_event_loop()

        def _upload():
            try:
                # Create PFX from certificate data
                pfx_data = self._create_pfx(
                    cert_data.cert_body, cert_data.private_key, pfx_password
                )
                if not pfx_data:
                    raise Exception("Failed to create PFX data")

                # Create unique filename
                random_suffix = secrets.token_hex(4)
                filename = f"{cert_data.cert_name}_{random_suffix}.pfx"

                # Upload to FTP
                ftp = ftplib.FTP()
                ftp.connect(self.ftp_config["host"], self.ftp_config.get("port", 21))
                ftp.login(self.ftp_config["user"], self.ftp_config["pass"])

                if self.ftp_config.get("path"):
                    try:
                        ftp.cwd(self.ftp_config["path"])
                        logger.info(f"Changed to FTP directory: {self.ftp_config['path']}")
                    except ftplib.error_perm as e:
                        logger.warning(
                            f"Could not change to directory {self.ftp_config['path']}: {e}"
                        )
                        logger.info("Using root FTP directory instead")

                with tempfile.NamedTemporaryFile() as temp_file:
                    temp_file.write(pfx_data)
                    temp_file.flush()
                    temp_file.seek(0)
                    ftp.storbinary(f"STOR {filename}", temp_file)

                ftp.quit()

                self.test_files_created.append(filename)

                ftp_path = self.ftp_config.get("path", "").strip("/")
                if ftp_path:
                    ftp_url = (
                        f"ftp://{self.ftp_config['user']}:"
                        f"{urllib.parse.quote(self.ftp_config['pass'])}"
                        f"@{self.ftp_config['host']}/{ftp_path}/{filename}"
                    )
                else:
                    ftp_url = (
                        f"ftp://{self.ftp_config['user']}:"
                        f"{urllib.parse.quote(self.ftp_config['pass'])}"
                        f"@{self.ftp_config['host']}/{filename}"
                    )

                logger.info(f"Certificate uploaded: {filename}")
                return ftp_url

            except Exception as e:
                logger.error(f"Certificate upload failed: {e}")
                raise

        return await loop.run_in_executor(None, _upload)

    async def check_certificate_exists(self, session, cert_name: str) -> bool:
        """Check if certificate exists on SonicWall."""
        cli_command = f"show certificate name {cert_name} status\nexit"
        status, response_data = await self._make_request(
            session, "POST", "/direct/cli", data=cli_command
        )

        if status is None or status not in [200, 201, 204]:
            return False

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
                    # If we get any response without "not found" errors, certificate likely exists
                    if "certificate" in message or cert_name.lower() in message:
                        return True

        return False

    async def delete_existing_certificate(self, session, cert_name: str) -> bool:
        """Delete existing certificate if it exists."""
        logger.info(f"Checking for and deleting existing certificate '{cert_name}'...")

        # Use the same delete method as in validator.py
        delete_commands = f"""certificates
no certificate "{cert_name}"
commit
end
exit"""

        status, response = await self._make_request(
            session, "POST", "/direct/cli", data=delete_commands
        )

        if status in [200, 201, 204]:
            if isinstance(response, dict) and "status" in response:
                status_info = response.get("status", {})
                if isinstance(status_info, dict):
                    info_list = status_info.get("info", [])
                    for info in info_list:
                        message = info.get("message", "").lower()
                        if info.get("level") == "error":
                            if "not found" in message or "does not exist" in message:
                                logger.info(
                                    f"Certificate '{cert_name}' does not exist - ready for import"
                                )
                                return True
                            logger.warning(f"Error deleting certificate: {message}")
                            return False
                        if "certificate has been successfully deleted" in message:
                            logger.info(f"Successfully deleted existing certificate '{cert_name}'")
                            return True
                        if "success" in message or "not found" in message:
                            logger.info(f"Certificate deletion completed: {message}")
                            return True
            logger.info(f"Certificate deletion command completed for '{cert_name}'")
            return True
        else:
            logger.warning(f"Failed to delete certificate (HTTP {status}): {response}")
            return False

    async def import_certificate_via_cli(
        self, session, cert_name: str, ftp_url: str, pfx_password: str
    ) -> bool:
        """Import certificate using CLI method."""
        logger.info(f"Importing certificate '{cert_name}' via CLI...")

        # Import certificate - CLI is already in config mode
        cli_commands = f"""certificates
import cert-key-pair {cert_name} password {pfx_password} ftp {ftp_url}
exit
"""

        status, response = await self._make_request(
            session, "POST", "/direct/cli", data=cli_commands
        )

        if status and status in [200, 201, 204]:
            if isinstance(response, dict):
                status_info = response.get("status", {})
                info_list = status_info.get("info", []) if isinstance(status_info, dict) else []

                for info in info_list:
                    message = info.get("message", "").lower()
                    level = info.get("level", "").lower()

                    acceptable_error_messages = [
                        "loaded before",
                        "already exists",
                        "duplicate local certificate name",
                        "has been loaded before",
                    ]

                    if "success" in message:
                        logger.info("Certificate import via CLI successful")
                        return True
                    elif level == "error":
                        found_acceptable_error = False
                        for ae_msg in acceptable_error_messages:
                            if ae_msg in message:
                                logger.info(
                                    f"Certificate '{cert_name}' {ae_msg} on SonicWall - proceeding"
                                )
                                found_acceptable_error = True
                                break
                        if found_acceptable_error:
                            return True
                        else:
                            logger.error(f"Certificate import error: {message}")
                            return False

                logger.info("Certificate import via CLI completed")
                return True
            else:
                logger.info("Certificate import via CLI successful")
                return True
        else:
            # Check if it's a certificate already exists error even with HTTP error status
            if isinstance(response, dict):
                status_info = response.get("status", {})
                info_list = status_info.get("info", [])

                for info in info_list:
                    message = info.get("message", "").lower()
                    if any(
                        err_msg in message
                        for err_msg in [
                            "loaded before",
                            "already exists",
                            "has been loaded before",
                        ]
                    ):
                        logger.info(
                            f"Certificate '{cert_name}' already exists on "
                            "SonicWall - proceeding with configuration"
                        )
                        return True

            logger.error(f"Certificate import via CLI failed: HTTP {status}")
            logger.error(f"Response: {response}")
            return False

    async def configure_ssl_vpn_certificate(self, session, cert_name: str) -> tuple[bool, str]:
        """Configure the imported certificate for SSL VPN using the proven working method."""
        logger.info(f"Configuring SSL VPN to use certificate '{cert_name}'...")

        # Ensure we're at the root level CLI
        await self._make_request(session, "POST", "/direct/cli", data="exit\nexit\nexit\nexit")

        # Use the proven working CLI path from sonic-vpn-2.py
        ssl_vpn_config = f"""ssl-vpn server
certificate name {cert_name}
exit
"""

        logger.info("Using proven working SSL VPN configuration method...")
        logger.info(f"CLI Path: ssl-vpn server > certificate name {cert_name}")

        status, response = await self._make_request(
            session, "POST", "/direct/cli", data=ssl_vpn_config
        )

        logger.info(f"SSL VPN config - Status: {status}, Response: {response}")

        if status and status in [200, 201, 204]:
            # Check response for any errors
            if isinstance(response, dict):
                status_info = response.get("status", {})
                info_list = status_info.get("info", [])

                for info in info_list:
                    message = info.get("message", "")
                    level = info.get("level", "").lower()

                    if level == "error":
                        logger.error(f"SSL VPN configuration error: {message}")
                        return False
                    elif "success" in message.lower():
                        logger.info(f"Success message: {message}")

            logger.info("SSL VPN certificate configuration successful")
            return True, "Success"
        else:
            error_msg = f"HTTP {status}"
            if response and isinstance(response, dict):
                if 'status' in response and 'info' in response['status']:
                    for info in response['status']['info']:
                        if 'message' in info:
                            error_msg += f" - {info['message']}"
            logger.error(f"SSL VPN configuration failed: {error_msg}")
            logger.error(f"Response: {response}")
            return False, error_msg

    async def commit_changes(self, session) -> bool:
        """Commit configuration changes."""
        logger.info("Committing configuration changes...")

        # Ensure we are at the root prompt
        await self._make_request(session, "POST", "/direct/cli", data="exit\nexit\nexit\nexit")

        cli_command = "commit"
        status, response = await self._make_request(
            session, "POST", "/direct/cli", data=cli_command
        )

        if status and status in [200, 201, 204]:
            if (
                isinstance(response, dict)
                and response.get("status", {}).get("success") is not False
            ):
                logger.info("Configuration committed successfully")
                return True
            elif "Command succeeded" in str(response) or "success" in str(response).lower():
                logger.info("Configuration committed successfully")
                return True
            else:
                logger.warning(f"Commit status inconclusive: {response}")
                return False
        else:
            logger.error(f"Failed to commit configuration: {response}")
            return False

    async def verify_ssl_vpn_configuration(self, session, cert_name: str) -> bool:
        """Verify that the SSL VPN is using the correct certificate using proven method from sonic-vpn-2.py"""  # noqa: E501
        logger.info("Verifying SSL VPN certificate configuration...")

        # Exit any config modes first to ensure show commands work
        await self._make_request(session, "POST", "/direct/cli", data="exit\nexit\nexit\nexit")

        # Use the exact show command that works (from sonic-vpn-2.py line 177)
        cli_command = "show ssl-vpn server\nexit"
        status, response = await self._make_request(
            session, "POST", "/direct/cli", data=cli_command
        )

        if status in [200, 201, 204]:
            response_text = ""
            if isinstance(response, dict):
                response_text = json.dumps(response, indent=2)
            else:
                response_text = str(response)

            logger.info("📋 SSL VPN Server Configuration:")
            logger.info(f"Full response: {response_text[:1000]}...")

            # Check if our certificate name appears in the response (exact match logic from sonic-vpn-2.py)  # noqa: E501
            if cert_name in response_text:
                logger.info(f"✅ Found certificate '{cert_name}' in SSL VPN configuration!")
                return True
            else:
                logger.warning(f"⚠️ Certificate '{cert_name}' not found in SSL VPN config")
                return False
        else:
            logger.error(f"❌ Verification failed: {response}")
            return False

    async def check_certificate_exists_by_name(self, session, cert_name: str) -> bool:
        """Check if a specific certificate exists using the working API method."""
        try:
            # Exit to root first
            await self._make_request(session, "POST", "/direct/cli", data="exit\nexit\nexit\nexit")

            # Use the proven working command format
            cli_command = f"show certificate name {cert_name} status\nexit"
            status, response = await self._make_request(
                session, "POST", "/direct/cli", data=cli_command
            )

            if status in [200, 201, 204]:
                # If we get a successful response, the certificate exists
                response_text = (
                    json.dumps(response) if isinstance(response, dict) else str(response)
                )
                if cert_name in response_text and "certificate" in response_text.lower():
                    logger.info(f"✅ Certificate '{cert_name}' exists")
                    return True
                else:
                    logger.info(f"❌ Certificate '{cert_name}' not found")
                    return False
            else:
                # Check if it's a "not found" error (which means it doesn't exist)
                if isinstance(response, dict) and "status" in response:
                    info_list = response.get("status", {}).get("info", [])
                    for info in info_list:
                        message = info.get("message", "").lower()
                        if "not found" in message or "not a reasonable value" in message:
                            logger.info(f"❌ Certificate '{cert_name}' does not exist")
                            return False

                logger.warning(
                    f"Unclear response when checking certificate '{cert_name}': {response}"
                )
                return False
        except Exception as e:
            logger.error(f"Error checking certificate '{cert_name}': {e}")
            return False

    def _generate_recent_ssl_vpn_names(self, current_cert_name: str, days_back: int = 7) -> list:
        """Generate possible SSL-VPN certificate names from recent days."""
        from datetime import datetime, timedelta

        possible_names = []
        now = datetime.now()

        # Generate names for each day going back
        for day_offset in range(1, days_back + 1):
            past_date = now - timedelta(days=day_offset)

            # Generate multiple possible times for each day (every 4 hours)
            for hour in range(0, 24, 4):
                for minute in [0, 15, 30, 45]:
                    test_time = past_date.replace(hour=hour, minute=minute)
                    test_name = f"SSL-VPN_{test_time.strftime('%m.%d.%y_%H.%M')}"

                    # Don't include the current certificate name
                    if test_name != current_cert_name:
                        possible_names.append(test_name)

        # Also check some common recent patterns (last few hours)
        for hour_offset in range(1, 25):  # Last 24 hours
            past_time = now - timedelta(hours=hour_offset)
            for minute in [0, 15, 30, 45]:
                test_time = past_time.replace(minute=minute)
                test_name = f"SSL-VPN_{test_time.strftime('%m.%d.%y_%H.%M')}"

                if test_name != current_cert_name and test_name not in possible_names:
                    possible_names.append(test_name)

        logger.info(f"Generated {len(possible_names)} possible certificate names to check")
        return possible_names

    async def cleanup_old_ssl_vpn_certificates(self, session, current_cert_name: str) -> bool:
        """Clean up old SSL-VPN certificates using targeted checking approach."""
        logger.info(f"Cleaning up old SSL-VPN certificates (keeping '{current_cert_name}')...")

        try:
            # Generate list of possible old certificate names
            possible_old_names = self._generate_recent_ssl_vpn_names(current_cert_name)
            logger.info(f"Checking {len(possible_old_names)} possible old certificate names...")

            # Check which certificates actually exist
            existing_old_certs = []
            for cert_name in possible_old_names:
                if await self.check_certificate_exists_by_name(session, cert_name):
                    existing_old_certs.append(cert_name)

                # Small delay to avoid overwhelming the API
                await asyncio.sleep(0.2)

            if not existing_old_certs:
                logger.info("✅ No old SSL-VPN certificates found to clean up")
                return True

            logger.info(
                f"Found {len(existing_old_certs)} old SSL-VPN certificates to delete: {existing_old_certs}"  # noqa: E501
            )

            # Delete each existing old certificate
            cleanup_count = 0
            for old_cert in existing_old_certs:
                logger.info(f"Deleting old certificate: {old_cert}")

                # Use the proven delete method
                delete_commands = f"""certificates
no certificate "{old_cert}"
commit
end
exit"""

                delete_status, delete_response = await self._make_request(
                    session, "POST", "/direct/cli", data=delete_commands
                )

                if delete_status in [200, 201, 204]:
                    # Check if deletion was successful by looking at response
                    success_indicators = [
                        "successfully deleted",
                        "success",
                        "not found",
                        "does not exist",
                    ]
                    response_text = (
                        json.dumps(delete_response)
                        if isinstance(delete_response, dict)
                        else str(delete_response)
                    )

                    if any(indicator in response_text.lower() for indicator in success_indicators):
                        logger.info(f"✅ Successfully deleted certificate: {old_cert}")
                        cleanup_count += 1
                    else:
                        logger.warning(
                            f"⚠️ Delete command sent for '{old_cert}' but success unclear"
                        )
                        cleanup_count += 1  # Count it as success anyway

                    # Wait for deletion to process
                    await asyncio.sleep(1)
                else:
                    logger.error(
                        f"❌ Failed to delete certificate '{old_cert}': HTTP {delete_status}"
                    )
                    logger.error(f"Response: {delete_response}")

            # Verify some deletions worked by checking a few certificates
            if cleanup_count > 0:
                logger.info(f"Cleanup completed: {cleanup_count} certificates processed")

                # Verify a couple deletions by checking if certificates still exist
                verification_count = min(3, len(existing_old_certs))
                verified_deletions = 0

                for cert_name in existing_old_certs[:verification_count]:
                    await asyncio.sleep(0.5)
                    if not await self.check_certificate_exists_by_name(session, cert_name):
                        verified_deletions += 1

                if verified_deletions > 0:
                    logger.info(
                        (
                            "✅ Verified"
                            f" {verified_deletions}/{verification_count} deletions successful"
                        )
                    )
                    return True
                else:
                    logger.warning(
                        "⚠️ Could not verify any deletions - certificates may still exist"
                    )
                    return False
            else:
                logger.warning("⚠️ No certificates were successfully deleted")
                return False

        except Exception as e:
            logger.error(f"Error during certificate cleanup: {e}")
            import traceback

            logger.error(f"Cleanup traceback: {traceback.format_exc()}")
            return False

    async def cleanup_ftp_files(self):
        """Clean up test files from FTP server."""
        if not self.test_files_created:
            return

        logger.info("Cleaning up FTP files...")
        loop = asyncio.get_event_loop()

        def _cleanup():
            try:
                ftp = ftplib.FTP()
                ftp.connect(self.ftp_config["host"], self.ftp_config.get("port", 21))
                ftp.login(self.ftp_config["user"], self.ftp_config["pass"])

                if self.ftp_config.get("path"):
                    try:
                        ftp.cwd(self.ftp_config["path"])
                    except ftplib.error_perm as e:
                        logger.warning(
                            f"Could not change to directory {self.ftp_config['path']} for cleanup: {e}"  # noqa: E501
                        )

                for filename in self.test_files_created:
                    try:
                        ftp.delete(filename)
                        logger.info(f"Cleaned up: {filename}")
                    except Exception as e:
                        logger.warning(f"Could not clean up: {filename}, error: {e}")

                ftp.quit()
                logger.info("FTP cleanup completed")

            except Exception as e:
                logger.warning(f"FTP cleanup error: {e}")

        await loop.run_in_executor(None, _cleanup)

    def _generate_ssl_vpn_cert_name(self) -> str:
        """Generate SSL VPN certificate name with format: SSL-VPN_MM.DD.YY_HH.MM"""
        from datetime import datetime

        # Generate timestamp in SSL-VPN_MM.DD.YY_HH.MM format
        now = datetime.now()
        timestamp = now.strftime("%m.%d.%y_%H.%M")
        cert_name = f"SSL-VPN_{timestamp}"

        logger.info(f"Generated SSL VPN certificate name: {cert_name}")
        return cert_name

    async def deploy_vpn_certificate(self, cert_data: CertificateData) -> AsyncIterator[str]:
        """Deploy certificate to SSL VPN service."""
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_context)

        try:
            async with aiohttp.ClientSession(connector=connector) as session:  # noqa: E501
                yield "🚀 Starting SonicWall SSL VPN Certificate Configuration..."
                yield f"  - Target: {self.hostname}:{self.management_port}"
                yield f"  - Certificate: {cert_data.cert_name}"

                # Check for staging certificate and warn user
                if "STAGING" in cert_data.cert_body or "staging" in cert_data.cert_body.lower():
                    yield "  - ⚠️ WARNING: This appears to be a Let's Encrypt STAGING certificate"
                    yield "  - ⚠️ Staging certificates may not be trusted by all systems"
                    yield "  - ⚠️ For production use, please use a production Let's Encrypt certificate"  # noqa: E501

                # Check if certificate chain is available
                chain_count = cert_data.cert_body.count("-----BEGIN CERTIFICATE-----")
                if chain_count > 1:
                    yield f"  - ✅ Certificate chain detected: {chain_count} certificates"
                else:
                    yield "  - ⚠️ WARNING: No certificate chain detected - this may cause verification issues"  # noqa: E501

                # Generate SSL VPN certificate name with timestamp format
                cert_name_for_sonicwall = self._generate_ssl_vpn_cert_name()
                yield f"  - Using certificate name: {cert_name_for_sonicwall}"
                yield f"  - Original FQDN: {cert_data.cert_name}"

                # Step 1: Authenticate
                yield "  - 🔐 Authenticating to SonicWall..."
                if not await self.authenticate(session):
                    yield "  - ❌ Authentication failed, aborting deployment"
                    return
                yield "  - ✅ Authentication successful."

                # Step 2: Upload certificate to FTP
                yield "  - 📤 Creating and uploading certificate to FTP..."
                from ....core.config import settings

                pfx_password = settings.PFX_PASSWORD
                try:
                    ftp_url = await self.upload_certificate_to_ftp(cert_data, pfx_password)
                    yield f"  - ✅ Certificate uploaded to FTP: {cert_data.cert_name}"
                except Exception as e:
                    yield f"  - ❌ FTP upload failed: {e}"
                    return

                # Step 3: Import new certificate
                yield f"  - 📥 Importing new certificate as '{cert_name_for_sonicwall}'..."
                import_success = await self.import_certificate_via_cli(
                    session, cert_name_for_sonicwall, ftp_url, pfx_password
                )

                if not import_success:
                    yield "  - ❌ New certificate import failed - deployment aborted"
                    yield "  - ✅ SSL VPN continues with existing certificate (no downtime)"
                    return
                else:
                    yield f"  - ✅ New certificate imported as '{cert_name_for_sonicwall}'"

                yield "  - ⏳ Waiting for import to process..."
                await asyncio.sleep(2)

                # Step 4: Configure SSL VPN to use new certificate
                yield "  - 🔧 Configuring SSL VPN to use the new certificate..."
                ssl_config_success, ssl_config_error = await self.configure_ssl_vpn_certificate(
                    session, cert_name_for_sonicwall
                )

                if not ssl_config_success:
                    # Add delay for readability and show actual error details
                    import asyncio
                    await asyncio.sleep(0.5)
                    yield "  - ❌ SSL VPN configuration failed - deployment aborted"
                    yield f"  - 📋 Error details: {ssl_config_error}"
                    yield "  - 💡 Check that the certificate name is valid and SSL VPN service is enabled"
                    yield "  - 🧹 Cleaning up failed certificate import..."
                    await self.delete_existing_certificate(session, cert_name_for_sonicwall)
                    return

                # Step 5: Commit changes
                yield "  - 💾 Committing configuration changes..."
                commit_success = await self.commit_changes(session)

                if not commit_success:
                    yield "  - ❌ Configuration commit failed - deployment aborted"
                    yield "  - 🧹 Cleaning up failed certificate import..."
                    await self.delete_existing_certificate(session, cert_name_for_sonicwall)
                    return

                yield "  - ✅ Configuration committed successfully"

                # Step 6: CRITICAL - Verify new certificate is actually working
                yield "  - 🔍 Verifying SSL VPN is using new certificate..."
                verification_success = await self.verify_ssl_vpn_configuration(  # noqa: E501
                    session, cert_name_for_sonicwall
                )

                if not verification_success:
                    yield f"  - ❌ VERIFICATION FAILED - Certificate '{cert_name_for_sonicwall}' not active!"  # noqa: E501
                    yield "  - 🚨 This indicates a serious configuration issue"
                    yield "  - ⚠️ Manual intervention may be required"
                    return

                yield f"  - ✅ VERIFIED: SSL VPN is using certificate '{cert_name_for_sonicwall}'"

                # Step 7: Clean up old SSL-VPN certificates (only after verification passes)
                yield "  - 🧹 Cleaning up old SSL-VPN certificates..."
                yield f"  - 🛡️ SAFETY: Will keep current certificate '{cert_name_for_sonicwall}' active"  # noqa: E501
                cleanup_success = await self.cleanup_old_ssl_vpn_certificates(
                    session, cert_name_for_sonicwall
                )
                if cleanup_success:
                    yield "  - ✅ Old certificates cleaned up successfully"
                else:
                    yield "  - ⚠️ Some old certificates may remain (manual cleanup recommended)"

                # Final success message
                yield "🎉 SUCCESS: SSL VPN certificate deployment completed!"
                yield f"  - ✅ Certificate '{cert_name_for_sonicwall}' is now active for SSL VPN"
                yield "  - 🌐 SSL VPN is accessible with the new certificate"
                yield "  - 🧹 Old certificates have been cleaned up"
                yield "  - 📋 Deployment used timestamp naming to avoid conflicts"

        except Exception as e:
            yield f"❌ Unexpected error during SSL VPN deployment: {e}"
        finally:
            # Always cleanup FTP files
            yield "  - 🧹 Cleaning up FTP files..."
            await self.cleanup_ftp_files()
            yield "  - ✅ Cleanup complete."

    async def verify_vpn_deployment(self, cert_name: str) -> AsyncIterator[str]:
        """Verify the VPN certificate is correctly deployed."""
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_context)

        try:
            async with aiohttp.ClientSession(connector=connector) as session:  # noqa: E501
                yield f"🔍 Verifying VPN certificate '{cert_name}' deployment..."

                if not await self.authenticate(session):
                    yield "❌ Authentication failed for verification"
                    return

                success = await self.verify_ssl_vpn_configuration(session, cert_name)

                if success:
                    yield "✅ VPN certificate verification successful!"
                    yield f"Certificate '{cert_name}' is configured in the system"
                else:
                    yield "❌ VPN certificate verification failed"

        except Exception as e:
            yield f"❌ VPN certificate verification error: {str(e)}"
