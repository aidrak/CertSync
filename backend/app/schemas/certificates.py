from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import List, Optional, Any
import datetime
import re

class CertificateBase(BaseModel):
    common_name: str

class CertificateCreate(CertificateBase):
    certificate_body: str
    private_key: str
    dns_provider_account_id: int

class CertificateRequest(BaseModel):
    domains: List[str]
    dns_provider_account_id: int

class Certificate(CertificateBase):
    id: int
    expires_at: Optional[datetime.datetime] = None
    issued_at: Optional[datetime.datetime] = None
    certificate_body: Optional[str] = None
    private_key: Optional[str] = None
    dns_provider_account_id: Optional[int] = None
    pfx_path: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class PasswordData(BaseModel):
    password: str
