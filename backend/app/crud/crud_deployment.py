from sqlalchemy.orm import Session, joinedload
from app.db import models
from app.schemas import schemas
from app.db.models import DeploymentStatus
from typing import Optional

def create_deployment(db: Session, certificate_id: int, target_system_id: int, auto_renewal_enabled: bool = False, deployment_config: Optional[str] = None):
    db_deployment = models.Deployment(
        certificate_id=certificate_id,
        target_system_id=target_system_id,
        auto_renewal_enabled=auto_renewal_enabled,
        deployment_config=deployment_config,
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

def update_deployment_status(db: Session, deployment_id: int, status: DeploymentStatus, details: Optional[str] = None):
    db.query(models.Deployment).filter(models.Deployment.id == deployment_id).update(
        {"status": status, "details": details}
    )
    db.commit()
    return get_deployment(db, deployment_id)
