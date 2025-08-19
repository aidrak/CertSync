import json

from app.core.security import decrypt_secret, encrypt_secret
from app.db import models
from app.schemas import dns as dns_schemas
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


def create_dns_provider_account(db: Session, account: dns_schemas.DnsProviderAccountCreate):
    try:
        # Validate that credentials can be properly processed before saving
        test_encrypted = encrypt_secret(account.credentials)
        test_decrypted = decrypt_secret(test_encrypted)
        json.loads(test_decrypted)  # Just validate, don't store

        # If validation passes, proceed with actual creation
        encrypted_credentials = encrypt_secret(account.credentials)

        db_account = models.DnsProviderAccount(
            provider_type=account.provider_type,
            credentials=encrypted_credentials,
            managed_domain=account.managed_domain,
            company=account.company,
        )

        db.add(db_account)
        db.commit()
        db.refresh(db_account)
        return db_account

    except (json.JSONDecodeError, SQLAlchemyError, Exception) as e:
        db.rollback()  # Rollback on any error
        raise Exception(f"Failed to create DNS account: {str(e)}")


def get_dns_provider_account(db: Session, account_id: int):
    return (
        db.query(models.DnsProviderAccount)
        .filter(models.DnsProviderAccount.id == account_id)
        .first()
    )


def get_dns_provider_account_by_domain(db: Session, managed_domain: str, company: str):
    return (
        db.query(models.DnsProviderAccount)
        .filter(
            models.DnsProviderAccount.managed_domain == managed_domain,
            models.DnsProviderAccount.company == company,
        )
        .first()
    )


def get_dns_provider_accounts(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.DnsProviderAccount).offset(skip).limit(limit).all()


def update_dns_provider_account(
    db: Session, account_id: int, account: dns_schemas.DnsProviderAccountUpdate
):
    db_account = get_dns_provider_account(db, account_id)
    if db_account:
        update_data = account.model_dump(exclude_unset=True)
        if "credentials" in update_data and update_data["credentials"]:
            update_data["credentials"] = encrypt_secret(update_data["credentials"])
        for key, value in update_data.items():
            setattr(db_account, key, value)
        db.commit()
        db.refresh(db_account)
    return db_account


def delete_dns_provider_account(db: Session, account_id: int):
    try:
        db_account = (
            db.query(models.DnsProviderAccount)
            .filter(models.DnsProviderAccount.id == account_id)
            .first()
        )
        if db_account:
            # Check if the DNS provider is associated with any certificates
            associated_certificates = (
                db.query(models.Certificate)
                .filter(models.Certificate.dns_provider_account_id == account_id)
                .count()
            )
            if associated_certificates > 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot delete DNS provider. It is currently "
                    f"associated with {associated_certificates} certificate(s). "
                    f"Please reassign them before deleting.",
                )

            db.delete(db_account)
            db.commit()
        return db_account
    except SQLAlchemyError as e:
        db.rollback()
        raise Exception(f"Failed to delete DNS account: {str(e)}")
