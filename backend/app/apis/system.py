import logging
from datetime import datetime, timedelta
from typing import List

from app.core.config import settings
from app.crud import crud_system_setting
from app.db import models
from app.db.database import get_db
from app.dependencies import require_role
from app.schemas import schemas
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

router = APIRouter()
logger = logging.getLogger(__name__)


# Backup-related schemas
class BackupSettings(BaseModel):
    backup_enabled: bool = False
    backup_frequency: str = "daily"
    backup_time: str = "02:00:00"
    backup_retention_days: int = 30
    backup_location: str = "/app/backups"


class BackupHistory(BaseModel):
    id: int
    backup_date: datetime
    status: str
    file_size: int
    file_path: str


@router.get("/stats/")
def get_system_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("technician")),
):
    """
    Get system-wide statistics.
    """
    total_target_systems = db.query(models.TargetSystem).count()
    total_certificates = db.query(models.Certificate).count()
    total_dns_providers = db.query(models.DnsProviderAccount).count()

    thirty_days_from_now = datetime.utcnow() + timedelta(days=30)
    expiring_soon = (
        db.query(models.Certificate)
        .filter(models.Certificate.expires_at < thirty_days_from_now)
        .count()
    )

    return {
        "total_target_systems": total_target_systems,
        "total_certificates": total_certificates,
        "total_dns_providers": total_dns_providers,
        "expiring_soon": expiring_soon,
    }


@router.get("/log-level/", response_model=schemas.SystemSetting)
def get_log_level(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("technician")),
):
    """
    Get the current system-wide logging level.
    """
    setting = crud_system_setting.get_setting(db, key="LOGGING_LEVEL")
    if not setting:
        # This should ideally not happen as it's set on startup
        return schemas.SystemSetting(key="LOGGING_LEVEL", value="INFO")
    return setting


@router.post("/log-level/", response_model=schemas.SystemSetting)
def set_log_level(
    setting: schemas.SystemSettingCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    """
    Set the system-wide logging level.
    """
    if setting.key != "LOGGING_LEVEL":
        raise HTTPException(status_code=400, detail="Only LOGGING_LEVEL key is allowed")

    updated_setting = crud_system_setting.update_setting(db, setting=setting)

    # Reconfigure logging for the running application
    logging.getLogger().setLevel(updated_setting.value.upper())
    logger.info(
        "Logging level dynamically changed to %s by user '%s'",
        updated_setting.value.upper(),
        current_user.username,
    )

    return updated_setting


@router.get("/timezone/")
def get_timezone(
    current_user: models.User = Depends(require_role("technician")),
):
    """
    Get the current system timezone.
    """
    return {"timezone": settings.TZ}


@router.get("/backup-settings", response_model=BackupSettings)
def get_backup_settings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("technician")),
):
    """
    Get backup configuration settings.
    """
    # In a real implementation, these would be stored in the database
    return BackupSettings(
        backup_enabled=False,
        backup_frequency="daily",
        backup_time="02:00:00",
        backup_retention_days=30,
        backup_location="/app/backups",
    )


@router.post("/backup-settings")
def save_backup_settings(
    settings: BackupSettings,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    """
    Save backup configuration settings.
    """
    # For now, just log the settings. In a real implementation, save to
    # database
    logger.info(f"Backup settings updated by {current_user.username}: {settings}")
    return {"message": "Backup settings saved successfully"}


@router.get("/backup-history", response_model=List[BackupHistory])
def get_backup_history(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("technician")),
):
    """
    Get backup history.
    """
    # For now, return empty list. In a real implementation, query from
    # database
    return []


@router.post("/backup-now")
def backup_now(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    """
    Trigger an immediate backup.
    """
    # For now, just log the action. In a real implementation, trigger backup
    # process
    logger.info(f"Manual backup triggered by {current_user.username}")
    return {"message": "Backup started successfully"}


@router.get("/download-backup/{backup_id}")
def download_backup(backup_id: int, current_user: models.User = Depends(require_role("admin"))):
    """
    Download a specific backup file.
    """
    # For now, just return not found. In a real implementation, serve the
    # backup file
    raise HTTPException(status_code=404, detail="Backup file not found")


@router.post("/trigger-auto-renewal")
async def trigger_auto_renewal(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    """
    Manually trigger automatic certificate renewal check.
    This will check all deployments with auto-renewal enabled and process any
    that are due.
    """
    from app.services.renewal_scheduler import renewal_scheduler

    try:
        renewal_results = await renewal_scheduler.run_manual_check()

        successful_renewals = [r for r in renewal_results if r.get("success", False)]
        failed_renewals = [r for r in renewal_results if not r.get("success", False)]

        return {
            "message": "Manual renewal check completed",
            "total_checked": len(renewal_results),
            "successful": len(successful_renewals),
            "failed": len(failed_renewals),
            "results": renewal_results,
        }

    except Exception as e:
        logger.error(f"Manual renewal check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Renewal check failed: {str(e)}")
