from pydantic import BaseModel
from typing import Dict, Any, Optional
from app.db.models import DnsProviderType


class DnsProviderAccountBase(BaseModel):
    provider_type: DnsProviderType
    managed_domain: str
    company: str


class DnsProviderAccountCreate(DnsProviderAccountBase):
    credentials: str


class DnsProviderAccountUpdate(BaseModel):
    provider_type: Optional[DnsProviderType] = None
    credentials: Optional[str] = None
    managed_domain: Optional[str] = None
    company: Optional[str] = None


class DnsProviderAccount(DnsProviderAccountBase):
    id: int
    credentials: Dict[str, Any]  # For retrieval, credentials are decrypted objects

    class Config:
        from_attributes = True


class DnsProviderAccountTest(DnsProviderAccountBase):
    credentials: Dict[str, Any]  # For testing, credentials should be objects
