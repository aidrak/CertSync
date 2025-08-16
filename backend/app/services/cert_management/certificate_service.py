import logging
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from ...crud import crud_certificate
from ...schemas.schemas import CertificateCreate
from ...db.models import Certificate
from ...core.security import decrypt_secret

logger = logging.getLogger(__name__)

class CertificateService:
    def create_certificate_data(
        self,
        cert_name: str,
        cert_body: str,
        private_key: str,
        chain: Optional[str] = None
    ) -> dict:
        """Helper method to create CertificateData object"""
        return {
            "cert_name": cert_name,
            "cert_body": cert_body,
            "private_key": private_key,
            "chain": chain
        }

    def validate_certificate_data(self, cert_data: dict) -> bool:
        """Validate certificate data before deployment"""
        try:
            # Basic validation - check if certificate and key are present
            if not cert_data.get("cert_name") or not cert_data.get("cert_name").strip():
                logger.error("Certificate name is required")
                return False
            
            if not cert_data.get("cert_body") or not cert_data.get("cert_body").strip():
                logger.error("Certificate body is required")
                return False
            
            if not cert_data.get("private_key") or not cert_data.get("private_key").strip():
                logger.error("Private key is required")
                return False
            
            # Check if certificate contains PEM format markers
            if "-----BEGIN CERTIFICATE-----" not in cert_data.get("cert_body"):
                logger.error("Certificate body does not appear to be in PEM format")
                return False
            
            if "-----BEGIN" not in cert_data.get("private_key") or "PRIVATE KEY-----" not in cert_data.get("private_key"):
                logger.error("Private key does not appear to be in PEM format")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating certificate data: {str(e)}")
            return False
