import asyncio
import base64
import logging
import ssl
from typing import AsyncIterator, Optional, Tuple

import aiohttp

from ..base import CertificateData

logger = logging.getLogger(__name__)


class FortiGateDeployManager:
    """
    FortiGate SSL VPN Certificate Deployment Manager
    Extracted from tested forti-vpn.py script for production use
    """

    def __init__(
        self,
        hostname: str,
        api_key: str,
        management_port: int = 443,
        verify_ssl: bool = False,
    ):
        self.hostname = hostname
        self.api_key = api_key
        self.management_port = management_port
        self.verify_ssl = verify_ssl
        self.base_url = f"https://{hostname}:{management_port}/api/v2"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def _make_request(
        self, session, method: str, endpoint: str, data: Optional[dict] = None
    ) -> Tuple[int, dict]:
        """Make async API request to FortiGate."""
        ssl_context = ssl.create_default_context()
        if not self.verify_ssl:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        url = f"{self.base_url}{endpoint}"
        response = None

        try:
            if method.upper() == "POST":
                async with session.post(url, headers=self.headers, json=data) as response:
                    result = await response.json()
                    logger.info(f"POST {endpoint}: {response.status} - {result}")
                    return response.status, result
            elif method.upper() == "PUT":
                async with session.put(url, headers=self.headers, json=data) as response:
                    result = await response.json()
                    logger.info(f"PUT {endpoint}: {response.status} - {result}")
                    return response.status, result
            elif method.upper() == "GET":
                async with session.get(url, headers=self.headers) as response:
                    result = await response.json()
                    logger.info(f"GET {endpoint}: {response.status} - {result}")
                    return response.status, result
            elif method.upper() == "DELETE":
                async with session.delete(url, headers=self.headers) as response:
                    result = await response.json()
                    logger.info(f"DELETE {endpoint}: {response.status} - {result}")
                    return response.status, result
        except Exception as e:
            status_code = response.status if response else 0
            error_details = f"{status_code}, message='{str(e)}', url='{url}'"
            logger.error(f"Request failed: {error_details}")
            return status_code, {"error": error_details}
        return 0, {}

    async def create_vpn_certificate(self, cert_data: CertificateData) -> AsyncIterator[str]:
        """Create/import certificate for VPN assignment."""
        ssl_context = ssl.create_default_context()
        if not self.verify_ssl:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        connector = aiohttp.TCPConnector(ssl=ssl_context)

        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                yield f"Creating certificate '{cert_data.cert_name}' for VPN assignment..."

                # Base64 encode for monitor API
                cert_b64 = base64.b64encode(cert_data.cert_body.encode("utf-8")).decode("utf-8")
                key_b64 = base64.b64encode(cert_data.private_key.encode("utf-8")).decode("utf-8")

                payload = {
                    "type": "regular",
                    "certname": cert_data.cert_name,
                    "file_content": cert_b64,
                    "key_file_content": key_b64,
                    "scope": "global",
                }

                status, result = await self._make_request(
                    session, "POST", "/monitor/vpn-certificate/local/import", payload
                )

                if status == 200:
                    yield f"✅ Certificate '{cert_data.cert_name}' created successfully"
                elif status == 500 and result.get("error") == -23:
                    yield f"ℹ️ Certificate '{cert_data.cert_name}' already exists, continuing..."
                else:
                    yield f"❌ Failed to create certificate: {result}"

        except Exception as e:
            yield f"❌ Error creating certificate: {str(e)}"

    async def get_current_vpn_settings(self, session) -> tuple[bool, str, dict]:
        """Get current SSL VPN settings."""
        logger.info("Getting current SSL VPN settings...")

        status, result = await self._make_request(session, "GET", "/cmdb/vpn.ssl/settings")

        if status == 200:
            settings = result.get("results", {})
            current_cert = settings.get("servercert", "Not set")
            vpn_status = settings.get("status", "Unknown")

            logger.info(
                f"Current SSL VPN settings - Status: {vpn_status}, Certificate: {current_cert}"
            )
            return True, current_cert, settings
        else:
            logger.error(f"Failed to get VPN settings: {result}")
            return False, "", {}

    async def deploy_vpn_certificate(self, cert_data: CertificateData) -> AsyncIterator[str]:
        """Deploy certificate to SSL VPN service."""
        ssl_context = ssl.create_default_context()
        if not self.verify_ssl:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        connector = aiohttp.TCPConnector(ssl=ssl_context)

        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                yield "🚀 Starting FortiGate SSL VPN certificate deployment..."
                await asyncio.sleep(1)  # Allow user to see the start message

                # Step 1: Get current VPN settings
                yield "📋 Getting current SSL VPN settings..."
                await asyncio.sleep(1)  # Show progress step
                success, original_cert, settings = await self.get_current_vpn_settings(session)
                if not success:
                    yield "❌ Failed to get current VPN settings"
                    yield "💡 Check API key, FortiGate connectivity, and admin privileges"
                    return

                yield f"Current SSL VPN certificate: {original_cert}"
                await asyncio.sleep(1)  # Show current cert info

                # Step 2: Create/import certificate
                yield f"📋 Creating/importing certificate '{cert_data.cert_name}'..."
                await asyncio.sleep(1)  # Show import step
                async for message in self.create_vpn_certificate(cert_data):
                    yield message

                await asyncio.sleep(2)

                # Step 3: Set VPN certificate
                yield f"🔧 Setting SSL VPN certificate to '{cert_data.cert_name}'..."
                await asyncio.sleep(1)  # Show configuration step

                # Update only the server certificate
                payload = {"servercert": cert_data.cert_name}

                status, result = await self._make_request(
                    session, "PUT", "/cmdb/vpn.ssl/settings", payload
                )

                if status == 200:
                    yield f"✅ SSL VPN certificate set to '{cert_data.cert_name}' successfully!"
                    await asyncio.sleep(1)  # Show success message
                else:
                    yield f"❌ Failed to set VPN certificate: {result}"
                    return

                await asyncio.sleep(2)

                # Step 4: Verify assignment
                yield "🔍 Verifying SSL VPN certificate assignment..."
                await asyncio.sleep(1)  # Show verification step
                success, current_cert, _ = await self.get_current_vpn_settings(session)

                if success and current_cert == cert_data.cert_name:
                    yield "✅ VPN certificate assignment verified!"
                    yield "🎉 SSL VPN CERTIFICATE DEPLOYMENT SUCCESSFUL!"
                    yield (
                        f"✅ Certificate '{cert_data.cert_name}' is now the active SSL VPN "
                        "certificate"
                    )
                    yield f"🌐 SSL VPN URL: https://{self.hostname}:{self.management_port}"
                else:
                    yield "❌ VPN certificate assignment verification failed"
                    yield f"Expected: {cert_data.cert_name}, Current: {current_cert}"

        except Exception as e:
            yield f"❌ VPN certificate deployment failed: {str(e)}"

    async def verify_vpn_deployment(self, cert_name: str) -> AsyncIterator[str]:
        """Verify the VPN certificate is correctly deployed."""
        ssl_context = ssl.create_default_context()
        if not self.verify_ssl:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        connector = aiohttp.TCPConnector(ssl=ssl_context)

        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                yield f"🔍 Verifying VPN certificate '{cert_name}' deployment..."

                success, current_cert, settings = await self.get_current_vpn_settings(session)

                if success and current_cert == cert_name:
                    yield "✅ VPN certificate verification successful!"
                    yield f"Current SSL VPN certificate: {current_cert}"
                    yield f"VPN Status: {settings.get('status', 'Unknown')}"
                else:
                    yield "❌ VPN certificate verification failed"
                    yield f"Expected: {cert_name}, Current: {current_cert}"

        except Exception as e:
            yield f"❌ VPN certificate verification error: {str(e)}"

    async def restore_original_vpn_certificate(
        self, original_cert: str, test_cert: str
    ) -> AsyncIterator[str]:
        """Restore the original VPN certificate (for testing)."""
        if original_cert and original_cert != test_cert:
            ssl_context = ssl.create_default_context()
            if not self.verify_ssl:
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

            connector = aiohttp.TCPConnector(ssl=ssl_context)

            try:
                async with aiohttp.ClientSession(connector=connector) as session:
                    yield f"🔄 Restoring original VPN certificate '{original_cert}'..."

                    payload = {"servercert": original_cert}

                    status, result = await self._make_request(
                        session, "PUT", "/cmdb/vpn.ssl/settings", payload
                    )

                    if status == 200:
                        yield "✅ Original VPN certificate restored"
                    else:
                        yield f"❌ Failed to restore original VPN certificate: {result}"

            except Exception as e:
                yield f"❌ Error restoring original certificate: {str(e)}"
        else:
            yield "ℹ️ No original certificate to restore"
