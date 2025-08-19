from sqlalchemy.orm import Session

from ..db import models
from ..schemas import certificates as cert_schema


def get_hostname(db: Session, hostname_id: int):
    return db.query(models.Hostname).filter(models.Hostname.id == hostname_id).first()


def update_hostname(db: Session, hostname_id: int, hostname: cert_schema.HostnameUpdate):
    db_hostname = db.query(models.Hostname).filter(models.Hostname.id == hostname_id).first()
    if db_hostname:
        db_hostname.certificate_id = hostname.certificate_id
        db.commit()
        db.refresh(db_hostname)
    return db_hostname
