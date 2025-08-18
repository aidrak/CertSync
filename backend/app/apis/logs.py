import logging
from typing import List
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse
import asyncio

from app.crud import crud_log
from app.schemas.schemas import Log, FrontendLogCreate, LogCreate
from app.db.database import get_db
from app.dependencies import get_current_user, get_optional_current_user
from app.db.models import User as UserModel
from app.schemas.schemas import User as UserSchema
from app.services.log_streamer import log_streamer
from sqlalchemy.orm import joinedload

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_model=List[Log])
def read_logs(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """
    Retrieve logs from the database.
    """
    logger.debug(
        f"User '{current_user.username}' reading logs with skip: {skip}, limit: {limit}"
    )
    logs = (
        db.query(crud_log.models.Log)
        .options(joinedload(crud_log.models.Log.user))
        .order_by(crud_log.models.Log.timestamp.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return logs


@router.post("/frontend/", status_code=201)
def create_frontend_log(
    log: FrontendLogCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_optional_current_user),
):
    """
    Receive and process a log entry from the frontend.
    """
    user_id = None
    username = "anonymous"
    if current_user:
        user_schema = UserSchema.from_orm(current_user)
        user_id = user_schema.id
        username = user_schema.username

    logger.info(
        f"Received frontend log from user '{username}' - Level: {log.level}, "
        f"Message: {log.message}, Extra: {log.extra}"
    )

    target_url = "Unknown URL"
    if log.extra:
        target_url = log.extra.get("url", "Unknown URL")

    log_data = LogCreate(
        action="Frontend Event",
        target=target_url,
        level=log.level.upper(),
        message=log.message,
    )
    crud_log.create_log(db=db, log=log_data, user_id=user_id)

    return {"status": "ok"}


@router.get("/stream/{target}")
async def stream_logs(request: Request, target: str):
    """
    Stream logs for a specific target using Server-Sent Events.
    """
    queue = await log_streamer.subscribe(target)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15)
                    yield {"data": message}
                except asyncio.TimeoutError:
                    # Send a keep-alive comment every 15 seconds
                    yield {"event": "ping", "data": "keep-alive"}

        except asyncio.CancelledError:
            pass
        finally:
            log_streamer.unsubscribe(target, queue)

    return EventSourceResponse(event_generator())
