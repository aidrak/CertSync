from sqlalchemy.orm import Session
from app.db import models
from app.core.security import encrypt_secret, decrypt_secret
from datetime import datetime, timedelta
from cryptography.hazmat.primitives.serialization import pkcs12, load_pem_private_key
from cryptography.hazmat.primitives import serialization
from cryptography import x509
import re
import logging

logger = logging.getLogger(__name__)

def parse_certificate_expiration(certificate_body: str) -> datetime:
    """
    Parse the expiration date from a PEM-formatted certificate.
    Returns the actual expiration datetime from the certificate.
    """
    try:
        # Load the certificate from PEM format
        cert = x509.load_pem_x509_certificate(certificate_body.encode('utf-8'))
        
        # Get the expiration date (not_valid_after)
        expires_at = cert.not_valid_after
        
        logger.info(f"Certificate expires at: {expires_at}")
        return expires_at
        
    except Exception as e:
        logger.error(f"Failed to parse certificate expiration: {e}")
        # Fallback to 90 days from now if parsing fails
        fallback_date = datetime.utcnow() + timedelta(days=90)
        logger.warning(f"Using fallback expiration date: {fallback_date}")
        return fallback_date

def get_certificate(db: Session, certificate_id: int):
    return db.query(models.Certificate).filter(models.Certificate.id == certificate_id).first()


def get_certificates(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Certificate).offset(skip).limit(limit).all()

def create_certificate(db: Session, common_name: str, certificate_body: str, private_key: str, dns_provider_account_id: int):
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"--- crud_certificate.create_certificate called with common_name='{common_name}' ---")
    logger.info(f"🔍 DEBUG: Certificate body starts with: {certificate_body[:50]}...")
    logger.info(f"🔍 DEBUG: Private key starts with: {private_key[:50]}...")
    
    # Parse the actual expiration date from the certificate
    expires_at = parse_certificate_expiration(certificate_body)
    logger.info(f"Setting expiration to: {expires_at}")
    
    try:
        encrypted_private_key = encrypt_secret(private_key)
        logger.info("Private key encrypted successfully")
    except Exception as e:
        logger.error(f"🔍 DEBUG: Failed to encrypt private key: {e}")
        raise

    try:
        db_cert = models.Certificate(
            common_name=common_name,
            expires_at=expires_at,
            certificate_body=certificate_body,
            private_key=encrypted_private_key,
            dns_provider_account_id=dns_provider_account_id,
            pfx_path=f"/data/certsync/{common_name}.pfx"
        )
        logger.info("Certificate model created")
        
        db.add(db_cert)
        logger.info("Certificate added to session, awaiting commit from caller.")
        
        return db_cert
    except Exception as e:
        logger.error(f"Database operation failed: {e}")
        db.rollback()
        raise


def update_certificate(db: Session, certificate_id: int, certificate_body: str, private_key: str):
    """Update an existing certificate with new certificate body and private key (for renewal)"""
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"--- crud_certificate.update_certificate called for certificate_id={certificate_id} ---")
    
    db_cert = get_certificate(db, certificate_id)
    if not db_cert:
        logger.error(f"Certificate with ID {certificate_id} not found")
        return None
    
    # Parse the actual expiration date from the new certificate
    expires_at = parse_certificate_expiration(certificate_body)
    logger.info(f"Updating expiration to: {expires_at}")
    
    try:
        encrypted_private_key = encrypt_secret(private_key)
        logger.info("Private key encrypted successfully for renewal")
    except Exception as e:
        logger.error(f"Failed to encrypt private key during renewal: {e}")
        raise
    
    try:
        # Update the certificate fields
        db_cert.certificate_body = certificate_body
        db_cert.private_key = encrypted_private_key
        db_cert.expires_at = expires_at
        db_cert.issued_at = datetime.utcnow()  # Update issued date
        
        # Update renewal dates for all deployments using this certificate
        from .crud_deployment import update_deployment_renewal_dates_for_certificate
        update_deployment_renewal_dates_for_certificate(db, certificate_id)
        
        logger.info(f"Certificate {db_cert.common_name} updated successfully for renewal")
        return db_cert
    except Exception as e:
        logger.error(f"Database operation failed during certificate renewal: {e}")
        db.rollback()
        raise


def delete_certificate(db: Session, certificate_id: int):
    db_cert = get_certificate(db, certificate_id)
    if db_cert:
        db.delete(db_cert)
    return db_cert

def get_certs_expiring_soon(db: Session, days: int = 30):
    """
    Get certificates that are expiring within the specified number of days.
    """
    now = datetime.utcnow()
    expiration_threshold = now + timedelta(days=days)
    return db.query(models.Certificate).filter(models.Certificate.expires_at <= expiration_threshold).all()

def create_pfx(db: Session, certificate_id: int, password: str) -> bytes:
    db_cert = get_certificate(db, certificate_id)
    if not db_cert:
        raise ValueError("Certificate not found")

    private_key_pem = decrypt_secret(str(db_cert.private_key))
    private_key = load_pem_private_key(
        private_key_pem.encode('utf-8'),
        password=None
    )

    # Use regex to find all certificates in the PEM bundle
    pem_certs = re.findall(
        r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----",
        str(db_cert.certificate_body),
        re.DOTALL
    )
    
    if not pem_certs:
        raise ValueError("Could not parse any certificates from the certificate body.")

    # Load all found certificates
    certs = [x509.load_pem_x509_certificate(pem.encode('utf-8')) for pem in pem_certs]

    # The first certificate is the end-entity cert, the rest are the CA chain.
    end_entity_cert = certs[0]
    ca_certs = certs[1:] if len(certs) > 1 else None

    pfx_data = pkcs12.serialize_key_and_certificates(
        name=str(db_cert.common_name).encode('utf-8'),
        key=private_key,
        cert=end_entity_cert,
        cas=ca_certs,
        encryption_algorithm=serialization.BestAvailableEncryption(password.encode('utf-8'))
    )

    return pfx_data
