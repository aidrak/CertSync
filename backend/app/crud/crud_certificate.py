from sqlalchemy.orm import Session
from app.db import models
from app.core.security import encrypt_secret, decrypt_secret
from datetime import datetime, timedelta
from cryptography.hazmat.primitives.serialization import pkcs12, load_pem_private_key
from cryptography.hazmat.primitives import serialization
from cryptography import x509
import re

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
    
    # In a real scenario, you'd parse the cert body to get the real expiration
    expires_at = datetime.utcnow() + timedelta(days=90)
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
