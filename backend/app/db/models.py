from typing import Optional
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Text,
    Enum,
    UniqueConstraint,
    Boolean,
)
from sqlalchemy.orm import relationship
from .database import Base
import datetime
import enum


class UserRole(enum.Enum):
    admin = "admin"
    technician = "technician"
    readonly = "readonly"


class DnsProviderType(enum.Enum):
    cloudflare = "cloudflare"
    digitalocean = "digitalocean"


class TargetSystemType(enum.Enum):
    fortigate = "fortigate"
    panos = "panos"
    sonicwall = "sonicwall"
    iis = "iis"
    azure = "azure"


class DeploymentStatus(enum.Enum):
    pending = "pending"
    success = "success"
    failed = "failed"


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(Enum(UserRole))


class Log(Base):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    level = Column(String)
    action = Column(String)
    target = Column(String)
    message = Column(String(1000))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user = relationship("User")


class DnsProviderAccount(Base):
    __tablename__ = "dns_provider_accounts"
    id = Column(Integer, primary_key=True, index=True)
    provider_type = Column(Enum(DnsProviderType))
    credentials = Column(Text)  # Encrypted JSON blob
    managed_domain = Column(String, index=True)
    company = Column(String, nullable=False)
    certificates = relationship("Certificate", back_populates="dns_provider_account")

    __table_args__ = (
        UniqueConstraint(
            "managed_domain",
            "company",
            name="dns_provider_managed_domain_company_unique",
        ),
    )


class SystemSetting(Base):
    __tablename__ = "system_settings"
    key = Column(String, primary_key=True, index=True)
    value = Column(String)


class TargetSystem(Base):
    __tablename__ = "target_systems"
    id = Column(Integer, primary_key=True, index=True)
    system_name = Column(String, index=True)
    system_type = Column(Enum(TargetSystemType))
    api_key = Column(String)  # Encrypted
    public_ip = Column(String)
    vpn_port = Column(Integer, nullable=True)
    management_port = Column(Integer)
    admin_username = Column(String, nullable=True)
    admin_password = Column(String, nullable=True)  # Encrypted
    company = Column(String, nullable=False)
    deployments = relationship("Deployment", back_populates="target_system")

    __table_args__ = (
        UniqueConstraint(
            "system_name",
            "system_type",
            name="target_systems_system_name_type_unique",
        ),
    )


class Certificate(Base):
    __tablename__ = "certificates"
    id = Column(Integer, primary_key=True, index=True)
    common_name = Column(String, index=True, unique=True)
    expires_at = Column(DateTime)
    issued_at = Column(DateTime, default=datetime.datetime.utcnow)
    certificate_body = Column(Text)
    private_key = Column(Text)  # Encrypted
    pfx_path = Column(String, nullable=True)
    dns_provider_account_id = Column(
        Integer, ForeignKey("dns_provider_accounts.id"), nullable=False
    )
    dns_provider_account = relationship(
        "DnsProviderAccount", back_populates="certificates"
    )
    deployments = relationship("Deployment", back_populates="certificate")
    hostnames = relationship("Hostname", back_populates="certificate")

    __table_args__ = (
        UniqueConstraint("common_name", name="certificates_common_name_unique"),
    )


class Hostname(Base):
    __tablename__ = "hostnames"
    id = Column(Integer, primary_key=True, index=True)
    hostname = Column(String, index=True, unique=True)
    # --- FIX APPLIED HERE ---
    certificate_id: Optional[int] = Column(
        Integer, ForeignKey("certificates.id"), nullable=True
    )
    certificate = relationship("Certificate", back_populates="hostnames")


class Deployment(Base):
    __tablename__ = "deployments"
    id = Column(Integer, primary_key=True, index=True)
    certificate_id = Column(Integer, ForeignKey("certificates.id"), nullable=False)
    target_system_id = Column(Integer, ForeignKey("target_systems.id"), nullable=False)
    status = Column(Enum(DeploymentStatus), default=DeploymentStatus.pending)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )
    details = Column(Text, nullable=True)
    auto_renewal_enabled = Column(Boolean, default=False)
    last_deployed_at = Column(DateTime, nullable=True)
    next_renewal_date = Column(DateTime, nullable=True)
    deployment_config = Column(Text, nullable=True)

    certificate = relationship("Certificate", back_populates="deployments")
    target_system = relationship("TargetSystem", back_populates="deployments")


__all__ = [
    "User",
    "Log",
    "DnsProviderAccount",
    "SystemSetting",
    "TargetSystem",
    "Certificate",
    "Hostname",
    "Deployment",
    "UserRole",
    "DnsProviderType",
    "TargetSystemType",
    "DeploymentStatus",
]
