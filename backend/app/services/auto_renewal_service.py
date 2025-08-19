"""
Automatic Certificate Renewal Service

This service handles automatic renewal of certificates and subsequent deployment
to target systems. It's designed to be target-system agnostic for the renewal
part, then delegate to specific deployment handlers.
"""

import logging
from datetime import datetime
from typing import List

from sqlalchemy.orm import Session

from app.core.security import decrypt_secret
from app.crud import crud_certificate, crud_deployment
from app.db.database import SessionLocal
from app.db.models import Certificate, Deployment, DeploymentStatus
from app.services.dns_providers.factory import DnsProviderFactory
from app.services.le_management.le_service import LetsEncryptService

logger = logging.getLogger(__name__)


class AutoRenewalService:
    """
    Service for automatic certificate renewal and deployment.

    Architecture:
    1. Baseline Certificate Renewal (universal for all Cloudflare certificates)
    2. Target System Specific Deployment (SonicWall, etc.)
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def check_and_renew_due_certificates(self) -> List[dict]:
        """
        Check for certificates that are due for renewal and process them.
        Returns a list of renewal results.
        """
        db = SessionLocal()
        try:
            # Get certificates that are due for renewal (renewal date has passed)
            now = datetime.utcnow()
            due_deployments = (
                db.query(Deployment)
                .filter(
                    Deployment.auto_renewal_enabled.is_(True),
                    Deployment.next_renewal_date <= now,
                    Deployment.status != DeploymentStatus.pending,  # Don't renew if already pending
                )
                .all()
            )

            self.logger.info(f"Found {len(due_deployments)} deployments due for renewal")

            renewal_results = []

            for deployment in due_deployments:
                try:
                    result = await self.renew_certificate_and_deploy(db, deployment)
                    renewal_results.append(result)
                except Exception as e:
                    self.logger.error(f"Failed to renew deployment {deployment.id}: {e}")
                    renewal_results.append(
                        {
                            "deployment_id": deployment.id,
                            "certificate_name": deployment.certificate.common_name,
                            "success": False,
                            "error": str(e),
                        }
                    )

            return renewal_results

        finally:
            db.close()

    async def renew_certificate_and_deploy(self, db: Session, deployment: Deployment) -> dict:
        """
        Renew a certificate and deploy it to the target system.

        This implements the two-phase approach:
        1. Baseline Certificate Renewal (Cloudflare)
        2. Target System Specific Deployment
        """
        certificate = deployment.certificate
        target_system = deployment.target_system

        self.logger.info(
            f"Starting renewal for deployment {deployment.id}: "
            f"{certificate.common_name} -> {target_system.system_name}"
        )

        # Phase 1: Baseline Certificate Renewal (Universal for Cloudflare)
        try:
            renewal_result = await self.renew_certificate_cloudflare(db, certificate)
            if not renewal_result["success"]:
                return {
                    "deployment_id": deployment.id,
                    "certificate_name": certificate.common_name,
                    "success": False,
                    "phase": "certificate_renewal",
                    "error": renewal_result["error"],
                }
        except Exception as e:
            self.logger.error(f"Certificate renewal failed for {certificate.common_name}: {e}")
            return {
                "deployment_id": deployment.id,
                "certificate_name": certificate.common_name,
                "success": False,
                "phase": "certificate_renewal",
                "error": str(e),
            }

        # Phase 2: Target System Specific Deployment
        try:
            deployment_result = await self.deploy_to_target_system(db, deployment)
            return {
                "deployment_id": deployment.id,
                "certificate_name": certificate.common_name,
                "success": deployment_result["success"],
                "phase": "deployment",
                "renewal_logs": renewal_result.get("logs", []),
                "deployment_logs": deployment_result.get("logs", []),
                "error": deployment_result.get("error"),
            }
        except Exception as e:
            self.logger.error(
                f"Deployment failed for {certificate.common_name} to "
                f"{target_system.system_name}: {e}"
            )
            return {
                "deployment_id": deployment.id,
                "certificate_name": certificate.common_name,
                "success": False,
                "phase": "deployment",
                "renewal_logs": renewal_result.get("logs", []),
                "error": str(e),
            }

    async def renew_certificate_cloudflare(self, db: Session, certificate: Certificate) -> dict:
        """
        Phase 1: Baseline Certificate Renewal using Cloudflare.
        This is the same for all deployments using Cloudflare DNS.
        """
        self.logger.info(f"Phase 1: Renewing certificate {certificate.common_name} via Cloudflare")

        try:
            # Get DNS provider account
            dns_account = certificate.dns_provider_account
            if not dns_account or dns_account.provider_type != "cloudflare":
                raise Exception(
                    f"Certificate {certificate.common_name} is not using Cloudflare DNS"
                )

            # Get DNS provider
            dns_provider = DnsProviderFactory.get_provider(dns_account)

            # Prepare domains (assuming common_name is primary domain)
            domains = [certificate.common_name]

            # Create Let's Encrypt service
            le_service = LetsEncryptService()

            # Request new certificate
            cert_data = await le_service.request_certificate(
                domains=domains,
                dns_provider=dns_provider,
                email=f"admin@{domains[0].split('.', 1)[-1]}",  # Generate email from domain
            )

            # Update certificate in database
            updated_cert = crud_certificate.update_certificate(
                db=db,
                certificate_id=certificate.id,
                certificate_body=cert_data["certificate_body"],
                private_key=cert_data["private_key"],
            )

            if updated_cert:
                self.logger.info(f"Certificate {certificate.common_name} renewed successfully")
                return {
                    "success": True,
                    "certificate_id": certificate.id,
                    "new_expires_at": updated_cert.expires_at,
                    "logs": [f"Certificate {certificate.common_name} renewed via Cloudflare"],
                }
            else:
                raise Exception("Failed to update certificate in database")

        except Exception as e:
            self.logger.error(f"Cloudflare renewal failed for {certificate.common_name}: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": [f"Certificate renewal failed: {str(e)}"],
            }

    async def deploy_to_target_system(self, db: Session, deployment: Deployment) -> dict:
        """
        Phase 2: Deploy the renewed certificate to the target system.
        This delegates to the existing deployment logic (essentially the "Deploy" button).
        """
        target_system = deployment.target_system
        self.logger.info(
            f"Phase 2: Deploying certificate to "
            f"{target_system.system_type.value} system: {target_system.system_name}"
        )

        try:
            # Import the existing deployment logic
            from app.services.firewall_manager.base import CertificateData
            from app.services.firewall_manager.factory import FirewallManagerFactory

            # Prepare certificate data
            certificate = deployment.certificate
            cert_data = CertificateData(
                cert_name=certificate.common_name,
                cert_body=certificate.certificate_body,
                private_key=decrypt_secret(str(certificate.private_key)),
                chain=None,
            )

            # Get firewall manager for the target system
            firewall_manager = FirewallManagerFactory.get_manager(target_system)

            # Update deployment status to pending
            crud_deployment.update_deployment_status(
                db, deployment_id=deployment.id, status=DeploymentStatus.pending
            )

            # Perform deployment based on system type
            if target_system.system_type.value == "sonicwall":
                # Use SSL VPN deployment for SonicWall
                deployment_logs = []
                deployment_success = False

                async for message in firewall_manager.deploy_vpn_certificate(cert_data):
                    deployment_logs.append(message)
                    self.logger.info(f"Deployment progress: {message}")

                # Check for success
                deployment_success = any(
                    "SUCCESS" in log or "successful" in log.lower() for log in deployment_logs[-3:]
                )

                if deployment_success:
                    crud_deployment.update_deployment_status(
                        db,
                        deployment_id=deployment.id,
                        status=DeploymentStatus.success,
                        details="\n".join(deployment_logs[-10:]),
                    )

                    # Update last_deployed_at timestamp
                    from datetime import datetime

                    from app.db import models

                    db.query(models.Deployment).filter(
                        models.Deployment.id == deployment.id
                    ).update({"last_deployed_at": datetime.utcnow()})
                    db.commit()

                    self.logger.info(
                        f"Automatic deployment successful for {certificate.common_name}"
                    )
                    return {
                        "success": True,
                        "logs": deployment_logs,
                        "message": f"Certificate automatically deployed to "
                        f"{target_system.system_name}",
                    }
                else:
                    crud_deployment.update_deployment_status(
                        db,
                        deployment_id=deployment.id,
                        status=DeploymentStatus.failed,
                        details="\n".join(deployment_logs[-10:]),
                    )
                    return {
                        "success": False,
                        "logs": deployment_logs,
                        "error": "Deployment reported failure",
                    }
            else:
                # Handle other target system types as needed
                raise Exception(
                    f"Automatic deployment not yet implemented for "
                    f"{target_system.system_type.value}"
                )

        except Exception as e:
            crud_deployment.update_deployment_status(
                db,
                deployment_id=deployment.id,
                status=DeploymentStatus.failed,
                details=f"Automatic deployment error: {str(e)}",
            )
            raise


# Global service instance
auto_renewal_service = AutoRenewalService()
