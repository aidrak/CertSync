from typing import Optional

from sqlalchemy.orm import Session

from ..db import models
from ..schemas import schemas


def create_log(db: Session, log: schemas.LogCreate, user_id: Optional[int] = None):
    db_log = models.Log(**log.model_dump(), user_id=user_id)
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    return db_log


def get_logs(db: Session, skip: int = 0, limit: int = 100):
    return (
        db.query(models.Log).order_by(models.Log.timestamp.desc()).offset(skip).limit(limit).all()
    )
