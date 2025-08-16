import aiohttp
import ssl
import logging
from typing import AsyncIterator
from ..base import FirewallBase, CertificateData
from .cert_manager import FortiGateCertManager
from .deploy import FortiGateDeployManager

logger = logging.getLogger(__name__)

class FortiGateManager(FirewallBase):
    def __init__(self, hostname: str, api_key: str, management_port: int = 443, verify_ssl: bool = False):
        self.hostname = hostname
        self.api_key = api_key
        self.management_port = management_port
        self.verify_ssl = verify_ssl
        self.cert_manager = FortiGateCertManager(
            hostname=hostname,
            api_key=api_key,
            verify_ssl=verify_ssl
        )
        self.deploy_manager = FortiGateDeployManager(
            hostname=hostname,
            api_key=api_key,
            management_port=management_port,
            verify_ssl=verify_ssl
        )

    async def import_certificate(self, cert_data: CertificateData) -> bool:
        """Import certificate to FortiGate using REST API"""
        ssl_context = ssl.create_default_context()
        if not self.verify_ssl:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
        
        connector = aiohttp.TCPConnector(ssl=ssl_context)

        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                # Prepare certificate data
                payload = self.cert_manager._prepare_certificate_data(cert_data)
                
                # Check if certificate exists to decide between POST (create) and PUT (update)
                if await self.cert_manager.check_certificate_exists(session, cert_data.cert_name):
                    logger.info(f"Updating existing certificate {cert_data.cert_name} on {self.hostname}")
                    status, result = await self.cert_manager._make_request(session, "PUT", f"/cmdb/vpn.certificate/local/{cert_data.cert_name}", {"data": payload})
                else:
                    logger.info(f"Importing new certificate {cert_data.cert_name} to {self.hostname}")
                    status, result = await self.cert_manager._make_request(session, "POST", "/cmdb/vpn.certificate/local", {"data": payload})

                if status == 200:
                    logger.info(f"Successfully processed certificate {cert_data.cert_name}")
                    return True
                else:
                    logger.error(f"Failed to process certificate: {status} - {result}")
                    return False
                            
        except Exception as e:
            logger.error(f"Error importing certificate to FortiGate {self.hostname}: {str(e)}")
            return False

    async def apply_certificate(self, cert_name: str, service: str) -> bool:
        """Apply certificate to a specific service (admin, ssl-vpn, etc.)"""
        # This logic remains the same as it's not directly part of the import process
        return False

    async def commit_changes(self) -> bool:
        """FortiGate applies changes immediately, so no explicit commit is needed."""
        logger.info("FortiGate changes are applied immediately - no commit required")
        return True

    async def test_connection(self):
        """
        A placeholder to satisfy the FirewallBase abstract class.
        The actual connection test is handled by the FortiGateValidator class,
        which is called directly by the API for SSE.
        """
        logger.info(f"test_connection on manager for {self.hostname} called, but validation is handled by the dedicated validator.")
        yield "This is a placeholder. Use the dedicated Test Connection feature."
        return

    async def deploy_vpn_certificate(self, cert_data: CertificateData) -> AsyncIterator[str]:
        """Deploy certificate to FortiGate SSL VPN service."""
        async for message in self.deploy_manager.deploy_vpn_certificate(cert_data):
            yield message

    async def verify_vpn_deployment(self, cert_name: str) -> AsyncIterator[str]:
        """Verify the VPN certificate is correctly deployed."""
        async for message in self.deploy_manager.verify_vpn_deployment(cert_name):
            yield message
