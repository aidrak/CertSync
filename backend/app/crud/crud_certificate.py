"""
This module handles CRUD operations for certificates.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Union

from app.core.security import decrypt_secret, encrypt_secret
from app.db import models
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import dsa, ec, rsa
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    pkcs12,
)
from sqlalchemy.orm import Session

from . import crud_deployment

logger = logging.getLogger(__name__)

# Supported private key types for PKCS12 serialization
PKCS12PrivateKeyTypes = Union[rsa.RSAPrivateKey, dsa.DSAPrivateKey, ec.EllipticCurvePrivateKey]


def parse_certificate_expiration(certificate_body: str) -> datetime:
    """
    Parse the expiration date from a PEM-formatted certificate.
    Returns the actual expiration datetime from the certificate.
    """
    try:
        cert = x509.load_pem_x509_certificate(certificate_body.encode("utf-8"))
        expires_at = cert.not_valid_after
        logger.info("Certificate expires at: %s", expires_at)
        return expires_at
    except Exception as e:
        logger.error("Failed to parse certificate expiration: %s", e)
        fallback_date = datetime.utcnow() + timedelta(days=90)
        logger.warning("Using fallback expiration date: %s", fallback_date)
        return fallback_date


def get_certificate(db: Session, certificate_id: int):
    """Get a single certificate by ID."""
    return db.query(models.Certificate).filter(models.Certificate.id == certificate_id).first()


def get_certificates(db: Session, skip: int = 0, limit: int = 100):
    """Get all certificates."""
    return db.query(models.Certificate).offset(skip).limit(limit).all()


def create_certificate(
    db: Session,
    common_name: str,
    certificate_body: str,
    private_key: str,
    dns_provider_account_id: int,
):
    """Create a new certificate."""
    logger.info("Creating certificate for common_name='%s'", common_name)
    expires_at = parse_certificate_expiration(certificate_body)
    logger.info("Setting expiration to: %s", expires_at)

    try:
        encrypted_private_key = encrypt_secret(private_key)
        logger.info("Private key encrypted successfully")
    except Exception as e:
        logger.error("Failed to encrypt private key: %s", e)
        raise

    try:
        db_cert = models.Certificate(
            common_name=common_name,
            expires_at=expires_at,
            certificate_body=certificate_body,
            private_key=encrypted_private_key,
            dns_provider_account_id=dns_provider_account_id,
            pfx_path=f"/data/certsync/{common_name}.pfx",
        )
        logger.info("Certificate model created")
        db.add(db_cert)
        logger.info("Certificate added to session, awaiting commit.")
        return db_cert
    except Exception as e:
        logger.error("Database operation failed: %s", e)
        db.rollback()
        raise


def update_certificate(db: Session, certificate_id: int, certificate_body: str, private_key: str):
    """Update certificate for renewal."""
    logger.info("Updating certificate for certificate_id=%s", certificate_id)

    db_cert = get_certificate(db, certificate_id)
    if not db_cert:
        logger.error("Certificate with ID %s not found", certificate_id)
        return None

    expires_at = parse_certificate_expiration(certificate_body)
    logger.info("Updating expiration to: %s", expires_at)

    try:
        encrypted_private_key = encrypt_secret(private_key)
        logger.info("Private key encrypted successfully for renewal")
    except Exception as e:
        logger.error("Failed to encrypt private key during renewal: %s", e)
        raise

    try:
        setattr(db_cert, "certificate_body", certificate_body)
        setattr(db_cert, "private_key", encrypted_private_key)
        setattr(db_cert, "expires_at", expires_at)
        setattr(db_cert, "issued_at", datetime.utcnow())

        crud_deployment.update_deployment_renewal_dates_for_certificate(db, certificate_id)

        logger.info(
            "Certificate %s updated successfully for renewal",
            db_cert.common_name,
        )
        return db_cert
    except Exception as e:
        logger.error("DB operation failed during cert renewal: %s", e)
        db.rollback()
        raise


def delete_certificate(db: Session, certificate_id: int):
    """Delete a certificate."""
    db_cert = get_certificate(db, certificate_id)
    if db_cert:
        db.delete(db_cert)
    return db_cert


def get_certs_expiring_soon(db: Session, days: int = 30):
    """Get certificates expiring within a number of days."""
    now = datetime.utcnow()
    expiration_threshold = now + timedelta(days=days)
    return (
        db.query(models.Certificate)
        .filter(models.Certificate.expires_at <= expiration_threshold)
        .all()
    )


def create_pfx(db: Session, certificate_id: int, password: str) -> bytes:
    """
    Create a PFX file from a certificate.

    Args:
        db: The database session.
        certificate_id: The ID of the certificate.
        password: The password for the PFX file.

    Returns:
        The PFX file as bytes.
    """
    db_cert = get_certificate(db, certificate_id)
    if not db_cert:
        raise ValueError("Certificate not found")

    private_key_pem = decrypt_secret(str(db_cert.private_key))
    private_key = load_pem_private_key(private_key_pem.encode("utf-8"), password=None)

    if not isinstance(
        private_key,
        (rsa.RSAPrivateKey, dsa.DSAPrivateKey, ec.EllipticCurvePrivateKey),
    ):
        raise TypeError("Unsupported private key type for PKCS12.")

    pem_certs = re.findall(
        r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----",
        str(db_cert.certificate_body),
        re.DOTALL,
    )

    if not pem_certs:
        raise ValueError("Could not parse certificates from certificate body.")

    certs = [x509.load_pem_x509_certificate(pem.encode("utf-8")) for pem in pem_certs]

    end_entity_cert = certs
    ca_certs = certs[1:] if len(certs) > 1 else None

    pfx_data = pkcs12.serialize_key_and_certificates(
        name=str(db_cert.common_name).encode("utf-8"),
        key=private_key,
        cert=end_entity_cert,
        cas=ca_certs,
        encryption_algorithm=serialization.BestAvailableEncryption(password.encode("utf-8")),
    )

    return pfx_data
