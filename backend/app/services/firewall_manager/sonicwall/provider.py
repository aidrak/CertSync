import logging
import secrets
import aiohttp
import ssl
from typing import AsyncIterator, Dict, Any
from .validator import SonicWallValidator
from .cert_manager import SonicWallCertManager
from .deploy import SonicWallDeployManager
from ..base import FirewallBase as FirewallManager, CertificateData

logger = logging.getLogger(__name__)

class SonicWallManager(FirewallManager):
    def __init__(self, hostname, username, password, port=443, ftp_config: Dict[str, Any] = None, **kwargs):
        self.hostname = hostname
        self.username = username
        self.password = password
        self.port = port
        
        # Construct a settings object for the manager and validator
        self.settings = type('obj', (object,), {
            'public_ip': self.hostname,
            'admin_username': self.username,
            'api_key': self.password,
            'port': self.port
        })()
        self.cert_manager = SonicWallCertManager(self.settings)
        self.deploy_manager = SonicWallDeployManager(
            hostname=hostname,
            username=username,
            password=password,
            port=port,
            ftp_config=ftp_config
        )

    async def test_connection(self):
        """Tests the connection to the firewall and yields log messages."""
        logger.info(f"Initiating SonicWall connectivity test for {self.hostname}")
        validator = SonicWallValidator(self.settings)
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
            async for message in validator.run_complete_test(session):
                yield message
        logger.info(f"SonicWall connectivity test for {self.hostname} completed.")

    async def import_certificate(self, cert_data: CertificateData) -> bool:
        logger.info(f"Importing certificate '{cert_data.cert_name}' to SonicWall {self.hostname}")
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
            return await self.cert_manager.import_certificate_via_ftp(session, cert_data.cert_name, cert_data.private_key, cert_data.cert_body)

    async def delete_certificate(self, cert_name: str) -> bool:
        logger.info(f"Deleting certificate '{cert_name}' from SonicWall {self.hostname}")
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
            return await self.cert_manager.delete_certificate(session, cert_name)

    async def check_certificate_exists(self, cert_name: str) -> bool:
        logger.info(f"Checking for certificate '{cert_name}' on SonicWall {self.hostname}")
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
            return await self.cert_manager.check_certificate_exists(session, cert_name)

    async def apply_certificate(self, cert_name: str, service: str) -> bool:
        logger.info(f"Applying certificate on SonicWall {self.hostname}")
        # This will be implemented later
        return True

    async def commit_changes(self) -> bool:
        logger.info(f"Committing changes on SonicWall {self.hostname}")
        # This will be implemented later
        return True

    async def deploy_vpn_certificate(self, cert_data: CertificateData) -> AsyncIterator[str]:
        """Deploy certificate to SonicWall SSL VPN service."""
        async for message in self.deploy_manager.deploy_vpn_certificate(cert_data):
            yield message

    async def verify_vpn_deployment(self, cert_name: str) -> AsyncIterator[str]:
        """Verify the VPN certificate is correctly deployed."""
        async for message in self.deploy_manager.verify_vpn_deployment(cert_name):
            yield message
