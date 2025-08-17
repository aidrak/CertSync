from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List
import json
import logging

from app.db import models
from app.schemas import schemas as dns_schemas, dns as dns_schemas_dns
from app.crud import crud_dns
from app.dependencies import get_db, require_role
from app.core.security import decrypt_secret
from app.services.dns_providers.factory import DnsProviderFactory

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/dns-provider-accounts/", response_model=dns_schemas_dns.DnsProviderAccount)
def create_dns_provider_account(account: dns_schemas_dns.DnsProviderAccountCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_role("technician"))):
    try:
        # Validate input data
        if not account.managed_domain or not account.credentials or not account.company:
            raise HTTPException(status_code=400, detail="Missing required fields")
        
        # Check for existing account with the same name and company
        existing_account = crud_dns.get_dns_provider_account_by_domain(db, managed_domain=account.managed_domain, company=account.company)
        if existing_account:
            raise HTTPException(status_code=409, detail="An account with this name and company already exists.")
        
        # Validate credentials is proper JSON
        try:
            json.loads(account.credentials)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Credentials must be valid JSON")
        
        db_account = crud_dns.create_dns_provider_account(db=db, account=account)
        
        # Safely decrypt and return response
        decrypted_creds_json = decrypt_secret(str(db_account.credentials))
        parsed_credentials = json.loads(decrypted_creds_json)
        
        response_data = {
            "id": db_account.id,
            "provider_type": db_account.provider_type,
            "managed_domain": db_account.managed_domain,
            "company": db_account.company,
            "credentials": parsed_credentials
        }
        return dns_schemas_dns.DnsProviderAccount.model_validate(response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create DNS account: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create DNS account")

@router.get("/dns-provider-accounts/", response_model=List[dns_schemas_dns.DnsProviderAccount])
def read_dns_provider_accounts(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    try:
        accounts = crud_dns.get_dns_provider_accounts(db, skip=skip, limit=limit)
        result = []
        
        for account in accounts:
            try:
                decrypted_creds_json = decrypt_secret(str(account.credentials))
                parsed_credentials = json.loads(decrypted_creds_json)
                
                account_data = {
                    "id": account.id,
                    "provider_type": account.provider_type,
                    "managed_domain": account.managed_domain,
                    "company": account.company,
                    "credentials": parsed_credentials
                }
                result.append(dns_schemas_dns.DnsProviderAccount.model_validate(account_data))
                
            except Exception as e:
                logger.warning(f"Skipping corrupted account {account.id}: {str(e)}")
                # Skip corrupted accounts instead of failing entire request
                continue
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to fetch DNS accounts: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch DNS accounts")

@router.put("/dns-provider-accounts/{account_id}", response_model=dns_schemas_dns.DnsProviderAccount)
def update_dns_provider_account(account_id: int, account: dns_schemas_dns.DnsProviderAccountUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(require_role("technician"))):
    try:
        db_account = crud_dns.update_dns_provider_account(db=db, account_id=account_id, account=account)
        if db_account is None:
            raise HTTPException(status_code=404, detail="DNS Provider Account not found")
        
        decrypted_creds_json = decrypt_secret(str(db_account.credentials))
        parsed_credentials = json.loads(decrypted_creds_json)
        
        response_data = {
            "id": db_account.id,
            "provider_type": db_account.provider_type,
            "managed_domain": db_account.managed_domain,
            "company": db_account.company,
            "credentials": parsed_credentials
        }
        return dns_schemas_dns.DnsProviderAccount.model_validate(response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update DNS account {account_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update DNS account")

@router.delete("/dns-provider-accounts/{account_id}", response_model=dns_schemas_dns.DnsProviderAccount)
def delete_dns_provider_account(account_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_role("technician"))):
    try:
        db_account = crud_dns.delete_dns_provider_account(db=db, account_id=account_id)
        if db_account is None:
            raise HTTPException(status_code=404, detail="DNS Provider Account not found")
        
        decrypted_creds_json = decrypt_secret(str(db_account.credentials))
        parsed_credentials = json.loads(decrypted_creds_json)
        
        response_data = {
            "id": db_account.id,
            "provider_type": db_account.provider_type,
            "managed_domain": db_account.managed_domain,
            "company": db_account.company,
            "credentials": parsed_credentials
        }
        return dns_schemas_dns.DnsProviderAccount.model_validate(response_data)
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Failed to delete DNS account {account_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete DNS account")

@router.post("/dns-provider-accounts/test", response_model=dns_schemas_dns.DnsProviderAccountTest)
def test_dns_provider_account(account: dns_schemas_dns.DnsProviderAccountTest, request: Request, db: Session = Depends(get_db)):
    try:
        validator = DnsProviderFactory.get_validator(
            provider_type=account.provider_type,
            credentials=account.credentials,
            domain=account.managed_domain
        )
        if not validator.run_all_tests():
            raise HTTPException(status_code=400, detail=f"{account.provider_type.value.capitalize()} token test failed.")
        return account
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
