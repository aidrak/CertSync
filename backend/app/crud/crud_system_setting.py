from sqlalchemy.orm import Session
from ..db import models
from ..schemas import schemas


def get_setting(db: Session, key: str) -> models.SystemSetting:
    """
    Retrieve a setting from the database by its key.
    """
    return (
        db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
    )


def update_setting(
    db: Session, setting: schemas.SystemSettingCreate
) -> models.SystemSetting:
    """
    Update a setting in the database. If the setting does not exist, it will be created.
    """
    db_setting = get_setting(db, setting.key)
    if db_setting:
        db_setting.value = setting.value
    else:
        db_setting = models.SystemSetting(key=setting.key, value=setting.value)
        db.add(db_setting)

    db.commit()
    db.refresh(db_setting)
    return db_setting
