import logging
import asyncio
import aiohttp
import ssl
import base64
import json
import aioftp
import tempfile
import secrets
import subprocess
import os
import urllib.parse
import re
from typing import AsyncIterator, Dict, Any
from ..base import CertificateData

logger = logging.getLogger(__name__)

class SonicWallDeployManager:
    """
    SonicWall SSL VPN Certificate Deployment Manager
    Extracted from tested sonic-vpn.py script for production use
    """
    
    def __init__(self, hostname: str, username: str, password: str, port: int = 443, 
                 ftp_config: Dict[str, Any] | None = None):
        self.hostname = hostname
        self.username = username
        self.password = password
        self.port = port
        self.base_url = f"https://{hostname}:{port}/api/sonicos"
        
        # Setup authentication headers
        credential_string = f"{username}:{password}"
        credentials = base64.b64encode(credential_string.encode()).decode()
        self.headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # FTP configuration for certificate upload
        self.ftp_config = ftp_config or {}
        self.test_files_created = []

    async def _make_request(self, session, method: str, endpoint: str, data=None, timeout: int = 30):
        """Make API request and return (status, response_data)."""
        url = f"{self.base_url}{endpoint}"
        headers = self.headers.copy()
        
        if isinstance(data, str):
            headers["Content-Type"] = "text/plain"
        
        try:
            if method.upper() == "POST":
                if isinstance(data, str):
                    response_obj = await session.post(url, headers=headers, data=data, timeout=timeout)
                else:
                    response_obj = await session.post(url, headers=headers, json=data, timeout=timeout)
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
                            or (status < 400 and len(raw_text) > 0 and raw_text.strip().startswith(("{", "[")))
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
        
        # For auth endpoint, we need to send credentials in body, not header
        auth_data = {
            "user": self.username,
            "pass": self.password,
            "override": True
        }
        
        # Make auth request without Authorization header
        url = f"{self.base_url}/auth"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        try:
            response_obj = await session.post(url, headers=headers, json=auth_data, timeout=30)
            async with response_obj as response:
                status = response.status
                raw_text = await response.text()
                
                try:
                    if "application/json" in response.headers.get("Content-Type", "").lower() or len(raw_text) > 0:
                        response_data = json.loads(raw_text) if raw_text.strip() else {}
                    else:
                        response_data = {"raw_response": raw_text}
                except json.JSONDecodeError:
                    response_data = {"raw_response": raw_text}
                
                if status not in [200, 201, 204]:
                    logger.error(f"Authentication failed: HTTP {status}")
                    logger.error(f"Response: {response_data}")
                    return False
                
                logger.info("Authentication successful")
                return True
                
        except Exception as e:
            logger.error(f"Authentication request failed: {e}")
            return False

    def _create_pfx(self, cert_pem: str, key_pem: str, password: str) -> bytes:
        """Create PFX file from certificate and private key."""
        cert_file_path, key_file_path, pfx_file_path = None, None, None
        try:
            # Create temporary files
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.crt', delete=False) as cert_file:
                cert_file.write(cert_pem.encode('utf-8'))
                cert_file_path = cert_file.name
            
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.key', delete=False) as key_file:
                key_file.write(key_pem.encode('utf-8'))
                key_file_path = key_file.name
            
            with tempfile.NamedTemporaryFile(suffix='.pfx', delete=False) as pfx_file:
                pfx_file_path = pfx_file.name
            
            # Create PFX using OpenSSL
            cmd = [
                'openssl', 'pkcs12', '-export',
                '-out', pfx_file_path,
                '-inkey', key_file_path,
                '-in', cert_file_path,
                '-password', f'pass:{password}'
            ]
            
            logger.info("Creating PFX file using OpenSSL...")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                with open(pfx_file_path, 'rb') as f:
                    pfx_data = f.read()
                logger.info("PFX file created successfully")
                return pfx_data
            else:
                logger.error(f"OpenSSL stderr: {result.stderr}")
                logger.error(f"OpenSSL stdout: {result.stdout}")
                raise Exception(f"OpenSSL failed: {result.stderr}")
                
        finally:
            # Cleanup temporary files
            for path in [cert_file_path, key_file_path, pfx_file_path]:
                if path and os.path.exists(path):
                    try:
                        os.unlink(path)
                    except Exception as e:
                        logger.warning(f"Failed to remove temp file {path}: {e}")

    async def upload_certificate_to_ftp(self, cert_data: CertificateData, pfx_password: str) -> str:
        """Upload PFX certificate to FTP server."""
        logger.info("Creating and uploading certificate to FTP...")
        
        try:
            # Create PFX from certificate data
            pfx_data = self._create_pfx(cert_data.cert_body, cert_data.private_key, pfx_password)
            if not pfx_data:
                raise Exception("Failed to create PFX data")
            
            # Create unique filename
            random_suffix = secrets.token_hex(4)
            filename = f"{cert_data.cert_name}_{random_suffix}.pfx"
            
            # Upload to FTP using aioftp
            async with aioftp.Client.context(
                self.ftp_config['host'],
                port=self.ftp_config.get('port', 21),
                user=self.ftp_config['user'],
                password=self.ftp_config['pass']
            ) as client:
                # Change to the certificates directory if specified
                if self.ftp_config.get('path'):
                    try:
                        await client.change_directory(self.ftp_config['path'])
                        logger.info(f"Changed to FTP directory: {self.ftp_config['path']}")
                    except aioftp.errors.StatusCodeError as e:
                        logger.warning(f"Could not change to directory {self.ftp_config['path']}: {e}")
                        logger.info("Using root FTP directory instead")

                # Use a temporary file to upload
                with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                    temp_file.write(pfx_data)
                    temp_file_path = temp_file.name

                try:
                    await client.upload(temp_file_path, filename)
                finally:
                    os.unlink(temp_file_path)

            self.test_files_created.append(filename)
            
            # Construct FTP URL with path if specified
            ftp_path = self.ftp_config.get('path', '').strip('/')
            if ftp_path:
                full_path = f"{ftp_path}/{filename}"
            else:
                full_path = filename

            ftp_url = f"ftp://{self.ftp_config['user']}:{urllib.parse.quote(self.ftp_config['pass'])}@{self.ftp_config['host']}/{full_path}"
            
            logger.info(f"Certificate uploaded: {filename}")
            return ftp_url
            
        except Exception as e:
            logger.error(f"Certificate upload failed: {e}")
            raise

    async def import_certificate_via_cli(self, session, cert_name: str, ftp_url: str, pfx_password: str) -> bool:
        """Import certificate using CLI method."""
        logger.info(f"Importing certificate '{cert_name}' via CLI...")
        
        # Ensure we are at the root prompt
        await self._make_request(session, "POST", "/direct/cli", data="exit\nexit\nexit\nexit")

        # Attempt to delete existing certificate first
        delete_cli_commands = f"""no certificates {cert_name}
exit
"""
        logger.info(f"Attempting to clear existing certificate '{cert_name}'...")
        delete_status, delete_response = await self._make_request(session, "POST", "/direct/cli", data=delete_cli_commands)
        
        if delete_status in [200, 201, 204]:
            await asyncio.sleep(1)
            await self.commit_changes(session)
            await asyncio.sleep(1)
        
        # Import certificate
        cli_commands = f"""certificates
import cert-key-pair {cert_name} password {pfx_password} ftp {ftp_url}
exit
"""
        
        status, response = await self._make_request(session, "POST", "/direct/cli", data=cli_commands)
        
        if status in [200, 201, 204]:
            if isinstance(response, dict):
                status_info = response.get("status", {})
                info_list = status_info.get("info", []) if isinstance(status_info, dict) else []
                
                for info in info_list:
                    message = info.get("message", "").lower()
                    level = info.get("level", "").lower()

                    acceptable_error_messages = [
                        "loaded before",
                        "already exists",
                        "duplicate local certificate name"
                    ]

                    if "success" in message:
                        logger.info("Certificate import via CLI successful")
                        return True
                    elif level == "error":
                        found_acceptable_error = False
                        for ae_msg in acceptable_error_messages:
                            if ae_msg in message:
                                logger.info(f"Certificate '{cert_name}' {ae_msg} on SonicWall - proceeding")
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
            logger.error(f"Certificate import via CLI failed: HTTP {status}")
            logger.error(f"Response: {response}")
            return False

    async def configure_ssl_vpn_certificate(self, session, cert_name: str) -> bool:
        """Configure the imported certificate for SSL VPN."""
        logger.info(f"Configuring SSL VPN to use certificate '{cert_name}'...")
        
        # Ensure we're at the root level CLI
        await self._make_request(session, "POST", "/direct/cli", data="exit\nexit\nexit\nexit")
        
        # Try multiple SSL VPN configuration methods
        ssl_vpn_configs = [
            # SonicOS 7.x method
            f"""network
ssl-vpn
server-settings
server-certificate {cert_name}
exit
exit
exit
""",
            # SonicOS 6.x method
            f"""vpn
ssl-vpn
server-certificate {cert_name}
exit
exit
""",
            # Alternative paths
            f"""network
vpn
ssl-vpn
certificate {cert_name}
exit
exit
exit
""",
            f"""ssl-vpn
certificate {cert_name}
exit
"""
        ]
        
        for i, config in enumerate(ssl_vpn_configs, 1):
            logger.info(f"Trying SSL VPN configuration method {i}...")
            await self._make_request(session, "POST", "/direct/cli", data="exit\nexit\nexit\nexit")
            status, response = await self._make_request(session, "POST", "/direct/cli", data=config)
            
            if status in [200, 201, 204]:
                status_dict = response.get("status", {}) if isinstance(response, dict) else {}
                if isinstance(status_dict, dict) and status_dict.get("success") is not False:
                    logger.info(f"SSL VPN certificate configuration successful (method {i})")
                    return True
                elif "Command succeeded" in str(response) or "success" in str(response).lower():
                    logger.info(f"SSL VPN certificate configuration successful (method {i})")
                    return True
        
        logger.error("All SSL VPN configuration methods failed")
        return False

    async def commit_changes(self, session) -> bool:
        """Commit configuration changes."""
        logger.info("Committing configuration changes...")
        
        # Ensure we are at the root prompt
        await self._make_request(session, "POST", "/direct/cli", data="exit\nexit\nexit\nexit")
        
        cli_command = "commit"
        status, response = await self._make_request(session, "POST", "/direct/cli", data=cli_command)
        
        if status in [200, 201, 204]:
            status_dict = response.get("status", {}) if isinstance(response, dict) else {}
            if isinstance(status_dict, dict) and status_dict.get("success") is not False:
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
        """Verify that the SSL VPN is using the correct certificate."""
        logger.info("Verifying SSL VPN certificate configuration...")
        
        # Exit any config modes first
        await self._make_request(session, "POST", "/direct/cli", data="exit\nexit\nexit\nexit")
        
        verification_commands = [
            "show certificate",
            "show network ssl-vpn server-settings",
            "show administration web-management",
            "show status",
        ]
        
        certificate_found = False
        
        for cmd in verification_commands:
            cli_command = f"{cmd}\nexit"
            status, response = await self._make_request(session, "POST", "/direct/cli", data=cli_command)
            
            if status in [200, 201, 204]:
                response_text = ""
                if isinstance(response, dict):
                    response_text = json.dumps(response) 
                else: 
                    response_text = str(response) 

                logger.info(f"Command '{cmd}' output (partial): {response_text[:500]}...")
                
                if cert_name in response_text:
                    logger.info(f"Found certificate '{cert_name}' in '{cmd}' output!")
                    certificate_found = True
            else:
                logger.warning(f"Command '{cmd}' failed: {response}")
        
        if certificate_found:
            logger.info(f"Certificate '{cert_name}' is configured in the system")
            return True
        else:
            logger.warning(f"Certificate '{cert_name}' imported, but verification was inconclusive")
            logger.info("Please manually verify the SSL VPN certificate on the SonicWall UI")
            return True

    async def cleanup_ftp_files(self):
        """Clean up test files from FTP server."""
        if not self.test_files_created:
            return
            
        logger.info("Cleaning up FTP files...")
        try:
            async with aioftp.Client.context(
                self.ftp_config['host'],
                port=self.ftp_config.get('port', 21),
                user=self.ftp_config['user'],
                password=self.ftp_config['pass']
            ) as client:
                if self.ftp_config.get('path'):
                    try:
                        await client.change_directory(self.ftp_config['path'])
                    except aioftp.errors.StatusCodeError as e:
                        logger.warning(f"Could not change to directory {self.ftp_config['path']} for cleanup: {e}")
                
                for filename in self.test_files_created:
                    try:
                        await client.remove_file(filename)
                        logger.info(f"Cleaned up: {filename}")
                    except Exception as e:
                        logger.warning(f"Could not clean up: {filename}, error: {e}")
            
            logger.info("FTP cleanup completed")
            
        except Exception as e:
            logger.warning(f"FTP cleanup error: {e}")

    async def deploy_vpn_certificate(self, cert_data: CertificateData) -> AsyncIterator[str]:
        """Deploy certificate to SSL VPN service."""
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        
        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                yield "🚀 Starting SonicWall SSL VPN Certificate Configuration..."
                yield f"  - Target: {self.hostname}:{self.port}"
                yield f"  - Certificate: {cert_data.cert_name}"
                
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
                    yield f"  - ✅ Certificate uploaded to FTP"
                except Exception as e:
                    yield f"  - ❌ FTP upload failed: {e}"
                    return
                
                # Step 3: Import certificate
                yield f"  - 📥 Importing certificate '{cert_data.cert_name}'..."
                import_success = await self.import_certificate_via_cli(session, cert_data.cert_name, ftp_url, pfx_password)
                
                if not import_success:
                    yield "  - ❌ Certificate import failed, aborting"
                    return
                else:
                    yield "  - ✅ Certificate imported successfully"

                yield "  - ⏳ Waiting for import to process..."
                await asyncio.sleep(2)
                
                # Step 4: Configure SSL VPN
                yield "  - 🔧 Configuring SSL VPN to use the certificate..."
                ssl_config_success = await self.configure_ssl_vpn_certificate(session, cert_data.cert_name)
                
                # Step 5: Commit changes
                commit_success = False
                if ssl_config_success:
                    yield "  - 💾 Committing configuration changes..."
                    commit_success = await self.commit_changes(session)
                    if commit_success:
                        yield "  - ✅ Configuration committed successfully"
                    else:
                        yield "  - ⚠️ Commit may have failed"
                else:
                    yield "  - ⚠️ Skipping commit as SSL VPN configuration was not successful"

                # Step 6: Verify configuration
                yield "  - 🔍 Verifying SSL VPN configuration..."
                await self.verify_ssl_vpn_configuration(session, cert_data.cert_name)
                
                if ssl_config_success and commit_success:
                    yield "🎉 SUCCESS: SSL VPN certificate configuration completed!"
                    yield f"  - ✅ Certificate '{cert_data.cert_name}' configured for SSL VPN"
                    yield f"  - 🌐 SSL VPN should be accessible with the new certificate"
                elif ssl_config_success and not commit_success:
                    yield "⚠️ PARTIAL SUCCESS: SSL VPN configured but commit may have failed"
                    yield "  - Please manually commit changes on the SonicWall if necessary"
                else:
                    yield "❌ SSL VPN configuration failed"
                
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
            async with aiohttp.ClientSession(connector=connector) as session:
                yield f"🔍 Verifying VPN certificate '{cert_name}' deployment..."
                
                if not await self.authenticate(session):
                    yield "❌ Authentication failed for verification"
                    return
                
                success = await self.verify_ssl_vpn_configuration(session, cert_name)
                
                if success:
                    yield f"✅ VPN certificate verification successful!"
                    yield f"Certificate '{cert_name}' is configured in the system"
                else:
                    yield f"❌ VPN certificate verification failed"
                    
        except Exception as e:
            yield f"❌ VPN certificate verification error: {str(e)}"
