from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
import datetime
from ..db.models import UserRole, TargetSystemType


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)
    role: UserRole


class User(UserBase):
    id: int
    role: UserRole

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


class LogBase(BaseModel):
    level: str = Field(..., max_length=20)
    action: str = Field(..., max_length=100)
    target: str = Field(..., max_length=200)
    message: str = Field(..., max_length=1000)


class LogCreate(LogBase):
    pass


class Log(LogBase):
    id: int
    timestamp: datetime.datetime
    user: Optional[User] = None

    model_config = ConfigDict(from_attributes=True)


class FrontendLogCreate(BaseModel):
    level: str = Field(..., max_length=20)
    message: str = Field(..., max_length=2000)
    extra: Optional[dict] = None


# DnsProviderAccount schemas moved to app.schemas.dns to avoid conflicts


class SystemSettingBase(BaseModel):
    key: str = Field(..., min_length=1, max_length=100)
    value: str = Field(..., min_length=1, max_length=500)


class SystemSettingCreate(SystemSettingBase):
    pass


class SystemSetting(SystemSettingBase):
    model_config = ConfigDict(from_attributes=True)


class CertificateBase(BaseModel):
    common_name: str = Field(..., min_length=1, max_length=255)


class CertificateCreate(CertificateBase):
    dns_provider_account_id: int


class Certificate(CertificateBase):
    id: int
    expires_at: datetime.datetime
    issued_at: datetime.datetime
    dns_provider_account: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


class TargetSystemBase(BaseModel):
    system_name: str = Field(..., pattern=r"^[a-zA-Z0-9.\- ]+$", max_length=100)
    system_type: TargetSystemType
    public_ip: str
    vpn_port: Optional[int] = None
    management_port: int
    company: str
    admin_username: Optional[str] = None
    admin_password: Optional[str] = None


class TargetSystemCreate(TargetSystemBase):
    api_key: str


class TargetSystemUpdate(BaseModel):
    system_name: Optional[str] = Field(
        None, pattern=r"^[a-zA-Z0-9.\- ]+$", max_length=100
    )
    system_type: Optional[TargetSystemType] = None
    public_ip: Optional[str] = None
    vpn_port: Optional[int] = None
    management_port: Optional[int] = None
    api_key: Optional[str] = None
    company: Optional[str] = None
    admin_username: Optional[str] = None
    admin_password: Optional[str] = None


class TargetSystem(TargetSystemBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class DeploymentBase(BaseModel):
    certificate_id: int
    target_system_id: int
    auto_renewal_enabled: bool = False


class DeploymentCreate(DeploymentBase):
    deployment_config: Optional[str] = None


class DeploymentUpdate(BaseModel):
    certificate_id: Optional[int] = None
    target_system_id: Optional[int] = None
    auto_renewal_enabled: Optional[bool] = None
    deployment_config: Optional[str] = None


class Deployment(DeploymentBase):
    id: int
    status: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    details: Optional[str] = None
    last_deployed_at: Optional[datetime.datetime] = None
    next_renewal_date: Optional[datetime.datetime] = None
    deployment_config: Optional[str] = None
    certificate: "Certificate"
    target_system: "TargetSystem"

    model_config = ConfigDict(from_attributes=True)


class Hostname(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)
