from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..core.security import encrypt_secret
from ..db import models
from ..schemas import schemas


def get_target_system(db: Session, target_system_id: int):
    return db.query(models.TargetSystem).filter(models.TargetSystem.id == target_system_id).first()


def get_target_system_by_name(db: Session, system_name: str, system_type: str):
    return (
        db.query(models.TargetSystem)
        .filter(
            models.TargetSystem.system_name == system_name,
            models.TargetSystem.system_type == system_type,
        )
        .first()
    )


def get_target_systems(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.TargetSystem).offset(skip).limit(limit).all()


def create_target_system(db: Session, target_system: schemas.TargetSystemCreate):
    encrypted_api_key = encrypt_secret(target_system.api_key) if target_system.api_key else None
    encrypted_admin_password = (
        encrypt_secret(target_system.admin_password) if target_system.admin_password else None
    )
    db_target_system = models.TargetSystem(
        system_name=target_system.system_name,
        system_type=target_system.system_type,
        api_key=encrypted_api_key,
        public_ip=target_system.public_ip,
        vpn_port=target_system.vpn_port,
        management_port=target_system.management_port,
        company=target_system.company,
        admin_username=target_system.admin_username,
        admin_password=encrypted_admin_password,
    )
    db.add(db_target_system)
    db.commit()
    db.refresh(db_target_system)
    return db_target_system


def update_target_system(
    db: Session, target_system_id: int, target_system: schemas.TargetSystemUpdate
):
    db_target_system = get_target_system(db, target_system_id)
    if db_target_system:
        update_data = target_system.model_dump(exclude_unset=True)

        # Encrypt the new API key if it's provided
        if "api_key" in update_data and update_data["api_key"]:
            update_data["api_key"] = encrypt_secret(update_data["api_key"])

        if "admin_password" in update_data and update_data["admin_password"]:
            update_data["admin_password"] = encrypt_secret(update_data["admin_password"])

        for key, value in update_data.items():
            setattr(db_target_system, key, value)

        db.commit()
        db.refresh(db_target_system)
    return db_target_system


def delete_target_system(db: Session, target_system_id: int):
    db_target_system = (
        db.query(models.TargetSystem).filter(models.TargetSystem.id == target_system_id).first()
    )
    if db_target_system:
        if db_target_system.deployments:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete target system with active deployments.",
            )
        db.delete(db_target_system)
        db.commit()
    return db_target_system
