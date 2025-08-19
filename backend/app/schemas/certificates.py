import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class CertificateBase(BaseModel):
    common_name: str


class CertificateCreate(CertificateBase):
    certificate_body: str
    private_key: str
    dns_provider_account_id: int


class CertificateRequest(BaseModel):
    domains: List[str]
    dns_provider_account_id: int
    name: str
    hostname_id: int


class CertificateRequestBody(BaseModel):
    cert_request: CertificateRequest


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


class HostnameUpdate(BaseModel):
    certificate_id: int
