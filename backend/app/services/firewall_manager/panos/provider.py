import logging
import ssl
import xml.etree.ElementTree as ET

import aiohttp

from ..base import CertificateData, FirewallBase

logger = logging.getLogger(__name__)


class PanosManager(FirewallBase):
    def __init__(self, hostname: str, api_key: str, verify_ssl: bool = True):
        self.hostname = hostname
        self.api_key = api_key
        self.verify_ssl = verify_ssl
        self.base_url = f"https://{hostname}/api/"

    async def _api_request(self, params: dict) -> ET.Element:
        """Helper function to make API requests to PAN-OS"""
        ssl_context = ssl.create_default_context()
        if not self.verify_ssl:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        connector = aiohttp.TCPConnector(ssl=ssl_context)

        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(self.base_url, params=params) as response:
                response.raise_for_status()
                text = await response.text()
                return ET.fromstring(text)

    async def import_certificate(self, cert_data: CertificateData) -> bool:
        """Import certificate and private key to PAN-OS"""
        try:
            # PAN-OS expects the certificate and key in a single file
            keypair_content = f"{cert_data.private_key}\n{cert_data.cert_body}"

            # Use multipart/form-data for file upload
            data = aiohttp.FormData()
            data.add_field(
                "file",
                keypair_content,
                filename=f"{cert_data.cert_name}.pem",
                content_type="application/x-pem-file",
            )

            params = {
                "type": "import",
                "category": "keypair",
                "certificate-name": cert_data.cert_name,
                "format": "pem",
                "key": self.api_key,
            }

            ssl_context = ssl.create_default_context()
            if not self.verify_ssl:
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

            connector = aiohttp.TCPConnector(ssl=ssl_context)

            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(self.base_url, params=params, data=data) as response:
                    response_text = await response.text()
                    if response.status >= 400:
                        logger.error(
                            f"Failed to import certificate: {response.status} - {response_text}"
                        )
                        return False

                    root = ET.fromstring(response_text)
                    if root.attrib.get("status") == "success":
                        logger.info(f"Successfully imported certificate {cert_data.cert_name}")
                        return True
                    else:
                        logger.error(f"Failed to import certificate: {response_text}")
                        return False

        except Exception as e:
            logger.error(f"Error importing certificate to PAN-OS {self.hostname}: {str(e)}")
            return False

    async def apply_certificate(self, cert_name: str, service: str) -> bool:
        """Apply certificate to a service (e.g., ssl-tls-service-profile)"""
        try:
            if service.lower() != "ssl-tls-service-profile":
                logger.error(
                    f"Unsupported service for PAN-OS: {service}. "
                    "Only 'ssl-tls-service-profile' is supported."
                )
                return False

            xpath = (
                "/config/devices/entry[@name='localhost.localdomain']/vsys/entry"
                "[@name='vsys1']/ssl-tls-service-profile/entry[@name='default']"
            )
            element = f"<certificate>{cert_name}</certificate>"

            params = {
                "type": "config",
                "action": "set",
                "key": self.api_key,
                "xpath": xpath,
                "element": element,
            }

            root = await self._api_request(params)
            if root.attrib.get("status") == "success":
                logger.info(f"Successfully applied certificate {cert_name} to {service}")
                return True
            else:
                logger.error(
                    f"Failed to apply certificate: {ET.tostring(root, encoding='unicode')}"
                )
                return False

        except Exception as e:
            logger.error(f"Error applying certificate on PAN-OS {self.hostname}: {str(e)}")
            return False

    async def commit_changes(self) -> bool:
        """Commit changes on PAN-OS"""
        try:
            params = {"type": "commit", "cmd": "<commit></commit>", "key": self.api_key}
            root = await self._api_request(params)
            if root.attrib.get("status") == "success":
                logger.info("Successfully committed changes on PAN-OS")
                return True
            else:
                logger.error(f"Failed to commit changes: {ET.tostring(root, encoding='unicode')}")
                return False
        except Exception as e:
            logger.error(f"Error committing changes on PAN-OS {self.hostname}: {str(e)}")
            return False

    async def test_connection(self):
        """Test API connectivity by fetching system info, yielding log messages."""
        yield f"ℹ️ Attempting to connect to PAN-OS at {self.hostname}..."
        try:
            params = {
                "type": "op",
                "cmd": "<show><system><info></info></system></show>",
                "key": self.api_key,
            }
            yield f"   - Sending request to {self.base_url}"
            root = await self._api_request(params)

            if root.attrib.get("status") == "success":
                yield f"✅ Successfully connected to PAN-OS {self.hostname}."
                yield "Validation successful!"
            else:
                error_message = ET.tostring(root, encoding="unicode")
                yield f"❌ Connection test failed: {error_message}"
                logger.error(f"Connection test failed for PAN-OS {self.hostname}: {error_message}")

        except aiohttp.ClientError as e:
            yield (
                f"❌ Connection failed: Could not connect to {self.hostname}. "
                "Please check the IP/hostname and port."
            )
            logger.error(f"Connection error for PAN-OS {self.hostname}: {e}")
        except Exception as e:
            yield f"❌ An unexpected error occurred: {e}"
            logger.error(f"Connection test failed for PAN-OS {self.hostname}: {e}")
