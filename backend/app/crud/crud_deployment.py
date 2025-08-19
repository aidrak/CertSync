from datetime import datetime, timedelta
from typing import Optional

from app.db import models
from app.db.models import DeploymentStatus
from sqlalchemy.orm import Session, joinedload


def calculate_renewal_date(certificate_expires_at: datetime, days_before: int = 30) -> datetime:
    """
    Calculate the renewal date based on certificate expiration.
    Default is 30 days before expiration.
    """
    return certificate_expires_at - timedelta(days=days_before)


def create_deployment(
    db: Session,
    certificate_id: int,
    target_system_id: int,
    auto_renewal_enabled: bool = False,
    deployment_config: Optional[str] = None,
):
    # Get the certificate to calculate renewal date
    certificate = (
        db.query(models.Certificate).filter(models.Certificate.id == certificate_id).first()
    )

    # Calculate next renewal date (30 days before expiration)
    next_renewal_date = None
    if certificate and certificate.expires_at:
        next_renewal_date = calculate_renewal_date(certificate.expires_at)

    db_deployment = models.Deployment(
        certificate_id=certificate_id,
        target_system_id=target_system_id,
        auto_renewal_enabled=auto_renewal_enabled,
        deployment_config=deployment_config,
        next_renewal_date=next_renewal_date,
    )
    db.add(db_deployment)
    db.commit()
    db.refresh(db_deployment)
    return db_deployment


def get_deployments(db: Session, skip: int = 0, limit: int = 100):
    return (
        db.query(models.Deployment)
        .options(
            joinedload(models.Deployment.target_system),
            joinedload(models.Deployment.certificate).joinedload(
                models.Certificate.dns_provider_account
            ),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_deployment(db: Session, deployment_id: int):
    return db.query(models.Deployment).filter(models.Deployment.id == deployment_id).first()


def update_deployment_status(
    db: Session,
    deployment_id: int,
    status: DeploymentStatus,
    details: Optional[str] = None,
):
    db.query(models.Deployment).filter(models.Deployment.id == deployment_id).update(
        {"status": status, "details": details}
    )
    db.commit()
    return get_deployment(db, deployment_id)


def update_deployment_renewal_dates_for_certificate(db: Session, certificate_id: int):
    """
    Update renewal dates for all deployments using a specific certificate.
    This should be called when a certificate is renewed/updated.
    """
    # Get the certificate
    certificate = (
        db.query(models.Certificate).filter(models.Certificate.id == certificate_id).first()
    )
    if not certificate or not certificate.expires_at:
        return

    # Calculate new renewal date
    new_renewal_date = calculate_renewal_date(certificate.expires_at)

    # Update all deployments using this certificate
    db.query(models.Deployment).filter(models.Deployment.certificate_id == certificate_id).update(
        {"next_renewal_date": new_renewal_date}
    )
    db.commit()
