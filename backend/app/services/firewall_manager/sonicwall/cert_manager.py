import logging
import secrets

from .validator import SonicWallValidator

logger = logging.getLogger(__name__)


class SonicWallCertManager:
    def __init__(self, firewall_settings):
        self.validator = SonicWallValidator(firewall_settings)
        self.base_url = self.validator.base_url
        self.headers = self.validator.headers

    async def import_certificate_via_ftp(
        self, session, cert_name: str, private_key: str, cert_body: str
    ) -> bool:
        """Imports a certificate from an FTP URL using the validator's logic."""
        logger.info("Authenticating for certificate import...")
        if not await self.validator.authenticate(session):
            logger.error("Authentication failed. Cannot import certificate.")
            return False

        pfx_password = secrets.token_urlsafe(16)
        self.validator._create_pfx(cert_body, private_key, pfx_password)

        ftp_url, _ = await self.validator.upload_certificate_to_ftp(cert_name)
        if not ftp_url:
            logger.error("Failed to upload certificate to FTP.")
            return False

        logger.info(f"Importing certificate '{cert_name}' from {ftp_url}...")
        success = await self.validator.import_certificate(session, cert_name, ftp_url, pfx_password)

        await self.validator.logout(session)
        return success

    async def delete_certificate(self, session, cert_name: str) -> bool:
        """Deletes a certificate using the validator's logic."""
        logger.info("Authenticating for certificate deletion...")
        if not await self.validator.authenticate(session):
            logger.error("Authentication failed. Cannot delete certificate.")
            return False

        logger.info(f"Checking if certificate '{cert_name}' exists before deletion...")
        exists = await self.validator.check_certificate_exists(session, cert_name)
        if not exists:
            logger.info(f"Certificate '{cert_name}' does not exist. Nothing to delete.")
            await self.validator.logout(session)
            return True

        logger.info(f"Deleting certificate '{cert_name}'...")
        success = await self.validator.delete_certificate(session, cert_name)

        await self.validator.logout(session)
        return success

    async def check_certificate_exists(self, session, cert_name: str) -> bool:
        """Checks if a certificate exists using the validator."""
        if not await self.validator.authenticate(session):
            return False

        exists = await self.validator.check_certificate_exists(session, cert_name)
        await self.validator.logout(session)
        return exists
