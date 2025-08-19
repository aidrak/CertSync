import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..core.exceptions import ConflictError, NotFoundError, handle_sse_exception
from ..crud import crud_log, crud_target_system
from ..db.database import get_db
from ..db.models import TargetSystemType, User
from ..dependencies import get_current_user, require_admin_or_technician, require_role
from ..schemas import schemas

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/", response_model=schemas.TargetSystem)
def create_target_system(
    target_system: schemas.TargetSystemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("technician")),
):
    logger.debug(f"Attempting to create target_system with name: {target_system.system_name}")
    db_target_system = crud_target_system.get_target_system_by_name(
        db,
        system_name=target_system.system_name,
        system_type=target_system.system_type.value,
    )
    if db_target_system:
        logger.warning(f"Target system with name {target_system.system_name} already exists.")
        raise ConflictError("Target system name already registered")

    new_target_system = crud_target_system.create_target_system(db=db, target_system=target_system)
    logger.info(
        f"Target system '{new_target_system.system_name}' created "
        f"successfully by user '{current_user.username}'."
    )

    crud_log.create_log(
        db=db,
        log=schemas.LogCreate(
            level="info",
            action="Create Target System",
            target=f"Target System ID: {new_target_system.id}",
            message=(
                f"User '{current_user.username}' created a new target system: "
                f"{new_target_system.system_name}"
            ),
        ),
        user_id=getattr(current_user, "id", None),
    )

    return new_target_system


@router.get("/", response_model=List[schemas.TargetSystem])
def read_target_systems(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_technician),
):
    logger.debug(f"Reading target systems with skip: {skip}, limit: {limit}")
    target_systems = crud_target_system.get_target_systems(db, skip=skip, limit=limit)
    return target_systems


@router.get("/{target_system_id}", response_model=schemas.TargetSystem)
def read_target_system(
    target_system_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_technician),
):
    logger.debug(f"Reading target system with ID: {target_system_id}")
    db_target_system = crud_target_system.get_target_system(db, target_system_id=target_system_id)
    if db_target_system is None:
        logger.warning(f"Target system with ID {target_system_id} not found.")
        raise NotFoundError("Target system")
    return db_target_system


@router.put("/{target_system_id}", response_model=schemas.TargetSystem)
def update_target_system(
    target_system_id: int,
    target_system: schemas.TargetSystemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("technician")),
):
    logger.debug(f"Attempting to update target system with ID: {target_system_id}")
    db_target_system = crud_target_system.update_target_system(
        db, target_system_id=target_system_id, target_system=target_system
    )
    if db_target_system is None:
        logger.warning(f"Target system with ID {target_system_id} not found for update.")
        raise NotFoundError("Target system")

    logger.info(
        f"Target system '{db_target_system.system_name}' updated "
        f"successfully by user '{current_user.username}'."
    )
    crud_log.create_log(
        db=db,
        log=schemas.LogCreate(
            level="info",
            action="Update Target System",
            target=f"Target System ID: {db_target_system.id}",
            message=(
                f"User '{current_user.username}' updated target system: "
                f"{db_target_system.system_name}"
            ),
        ),
        user_id=getattr(current_user, "id", None),
    )

    return db_target_system


@router.delete("/{target_system_id}")
def delete_target_system(
    target_system_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("technician")),
):
    logger.debug(f"Attempting to delete target system with ID: {target_system_id}")
    db_target_system = crud_target_system.delete_target_system(
        db, target_system_id=target_system_id
    )
    if db_target_system is None:
        logger.warning(f"Target system with ID {target_system_id} not found for deletion.")
        raise NotFoundError("Target system")

    logger.info(
        f"Target system '{db_target_system.system_name}' deleted "
        f"successfully by user '{current_user.username}'."
    )
    crud_log.create_log(
        db=db,
        log=schemas.LogCreate(
            level="info",
            action="Delete Target System",
            target=f"Target System ID: {db_target_system.id}",
            message=(
                f"User '{current_user.username}' deleted a target system: "
                f"{db_target_system.system_name}"
            ),
        ),
        user_id=getattr(current_user, "id", None),
    )

    return db_target_system


@router.get("/test_connection_sse/{firewall_type}")
async def test_connection_sse(
    request: Request,
    firewall_type: TargetSystemType,
    system_name: str,
    company: str,
    public_ip: str,
    management_port: int,
    admin_username: Optional[str] = None,
    admin_password: Optional[str] = None,
    api_key: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    async def event_generator():
        from ..services.firewall_manager.factory import FirewallValidatorFactory

        yield f"data: ### Starting connection test for {firewall_type.value}... ###\n\n"
        await asyncio.sleep(1)

        try:
            # Construct a temporary TargetSystem object for the validator factory
            password = api_key or admin_password
            if not password:
                raise ValueError("Missing credentials. Provide either api_key or admin_password.")

            # The validator needs a consistent object that mimics the DB model.
            class FirewallSettings:
                def __init__(self, **kwargs):
                    self.__dict__.update(kwargs)

            firewall_settings = FirewallSettings(
                name=system_name,
                system_type=firewall_type,
                public_ip=public_ip,
                port=management_port,
                management_port=management_port,
                admin_username=admin_username,
                api_key=password,
                company=company,
                admin_password=admin_password,
            )

            validator = FirewallValidatorFactory.get_validator(firewall_settings)

            yield "data: ### Firewall validator initialized. Running test... ###\n\n"
            await asyncio.sleep(1)

            # The validator's run_complete_test method is an async generator
            async for msg in validator.run_complete_test():
                yield f"data: {msg}\n\n"
                await asyncio.sleep(0.1)

            yield "data: ### Test process finished. ###\n\n"
            await asyncio.sleep(1)

        except Exception as e:
            yield handle_sse_exception(e, "test connection")

        finally:
            yield "data: ###CLOSE###\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
