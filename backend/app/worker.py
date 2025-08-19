"""
This module manages the background worker for certificate renewals.
"""

import json
import logging

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .core.config import settings
from .core.security import decrypt_secret
from .crud import crud_certificate
from .crud.crud_certificate import update_certificate
from .db.database import SessionLocal
from .services.dns_providers.factory import DnsProviderFactory
from .services.le_management.le_service import LetsEncryptService

logger = logging.getLogger(__name__)

jobstores = {"default": SQLAlchemyJobStore(url=settings.DATABASE_URL)}
scheduler = AsyncIOScheduler(jobstores=jobstores)


async def renew_certificate(cert_id: int):
    """
    Renew a single certificate.
    """
    db = SessionLocal()
    try:
        cert = crud_certificate.get_certificate(db, cert_id)
        if not cert:
            logger.error("Certificate with ID %s not found.", cert_id)
            return

        logger.info("Renewing certificate for %s", cert.common_name)

        dns_account = cert.dns_provider_account
        if not dns_account:
            logger.error("No DNS provider account linked to certificate %s", cert.common_name)
            return

        decrypted_creds = decrypt_secret(dns_account.credentials)
        credentials = json.loads(decrypted_creds)

        dns_provider = DnsProviderFactory.get_provider(
            provider_type=dns_account.provider_type,
            credentials=credentials,
            domain=str(cert.common_name),
        )

        if not dns_provider:
            logger.error("Unsupported DNS provider type: %s", dns_account.provider_type.value)
            return

        le_service = LetsEncryptService(
            email=settings.LE_EMAIL,
            dns_provider=dns_provider,
            staging=settings.LE_STAGING,
        )

        domains = [str(cert.common_name)]
        private_key, cert_body, _, _ = await le_service.request_certificate(domains)

        update_certificate(
            db=db,
            certificate_id=getattr(cert, "id"),
            certificate_body=cert_body,
            private_key=private_key,
        )
        db.commit()

        logger.info("Successfully renewed certificate for %s", cert.common_name)

    finally:
        db.close()


async def check_certs_for_renewal():
    """
    Check for certificates that are due for renewal and schedule renewal jobs.
    """
    logger.info("Checking for certificates to renew...")
    db = SessionLocal()
    try:
        expiring_certs = crud_certificate.get_certs_expiring_soon(db)
        for cert in expiring_certs:
            scheduler.add_job(renew_certificate, args=[cert.id])
    finally:
        db.close()


async def start_scheduler():
    """Start the scheduler and add the recurring job."""
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started.")

    if scheduler.get_job("check_certs_for_renewal_job"):
        scheduler.remove_job("check_certs_for_renewal_job")

    scheduler.add_job(
        check_certs_for_renewal,
        "interval",
        days=1,
        id="check_certs_for_renewal_job",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,
    )

    await check_certs_for_renewal()
