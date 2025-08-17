# app/main.py (Modified AGAIN for startup order)

import logging
import os
import time
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from .db import models
from .db.database import engine, SessionLocal
from .apis import target_systems, certificates, auth, logs, system, dns, deploy
from .crud import crud_user, crud_system_setting
from .schemas.schemas import UserCreate, SystemSettingCreate, UserRole
from .core.config import settings
from .core.exceptions import CertSyncError
from sqlalchemy.sql import text

logging.basicConfig(level=settings.LOGGING_LEVEL.upper())
logger = logging.getLogger(__name__)


app = FastAPI(title="CertSync", version="0.1.0")

@app.exception_handler(CertSyncError)
async def certsync_exception_handler(request: Request, exc: CertSyncError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message}
    )

def configure_logging_from_db():
    """Reads logging level from DB and reconfigures the root logger.
    Assumes SystemSetting table and default LOGGING_LEVEL exists or can be created."""
    db = SessionLocal()
    try:
        log_level_setting = crud_system_setting.get_setting(db, "LOGGING_LEVEL")
        if not log_level_setting:
            # If not in DB, use .env setting and create the DB entry
            level = settings.LOGGING_LEVEL.upper()
            initial_setting = SystemSettingCreate(key="LOGGING_LEVEL", value=level)
            crud_system_setting.update_setting(db, initial_setting) # This should create if not exists
            db.commit() # Commit the initial setting
            logger.info(f"Initialized LOGGING_LEVEL setting in DB to {level}.")
        else:
            level = log_level_setting.value.upper()
        
        logging.getLogger().setLevel(level)
        logger.info(f"Logging level set to {level} from database config.")
        
    except Exception as e:
        logger.error(f"Error configuring logging from DB: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()

origins = [
    "http://localhost:8877",
    "http://localhost:8233",
]
if settings.HOST_ADDRESS:
    host = f"http://{settings.HOST_ADDRESS}"
    origins.append(f"{host}:8877")
    origins.append(f"{host}:8233")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(set(origins)),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    logger.info(f"FastAPI app attempting to connect to DATABASE_URL: {settings.DATABASE_URL}")
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        logger.info("FastAPI app successfully connected to the database during startup check.")
    except Exception as e:
        logger.error(f"FastAPI app FAILED to connect to the database during startup check: {e}")
        # Consider a more robust error handling for production: maybe exit here
        # For development, proceeding might be useful to diagnose further
        # If DB connection isn't established, subsequent DB operations will fail anyway.
        return # Exit startup if DB connection fails

    # IMPORTANT: The order of calls matters here for a clean DB start after a wipe/fresh deployment

    # 1. Ensure all tables are created.
    # If you are using Alembic for migrations (which you are), it is *best practice*
    # to let Alembic handle all table creation and updates. `create_all` is typically
    # for initial setup or very simple projects without migrations.
    # However, since you *just* wiped the DB, and Alembic *should* have created the tables,
    # and if it fails to create a table (like system_settings) then the app will fail,
    # for now, let's keep it commented and trust Alembic.
    # If `alembic upgrade head` ran successfully, all tables *should* exist.
    # models.Base.metadata.create_all(bind=engine) # Keep commented IF you rely on Alembic

    # 2. Initialize critical system settings (like LOGGING_LEVEL)
    # This must happen BEFORE configure_logging_from_db tries to read it.
    # And it implicitly creates the `system_settings` table if `alembic upgrade head`
    # didn't manage to create it for some reason (less likely if it completed successfully).
    # Let's ensure a default for LOGGING_LEVEL exists by calling configure_logging_from_db()
    # which will insert it if it doesn't find it.
    configure_logging_from_db() # This will now initialize the setting if not present.

    # 3. Create the default admin user.
    create_default_admin()
    
    # 4. Start the automatic certificate renewal scheduler
    from app.services.renewal_scheduler import renewal_scheduler
    renewal_scheduler.start()

def create_default_admin():
    db = SessionLocal()
    try:
        # Check if the admin user already exists
        admin_user = crud_user.get_user_by_username(db, username=settings.DEFAULT_ADMIN_USER)
        if not admin_user:
            # Create the admin user if it doesn't exist
            user_in = UserCreate(
                username=settings.DEFAULT_ADMIN_USER,
                password=settings.DEFAULT_ADMIN_PASSWORD,
                role=UserRole.admin
            )
            crud_user.create_user(db=db, user=user_in)
            logger.info(f"Default admin user '{settings.DEFAULT_ADMIN_USER}' created.")
        else:
            logger.info(f"Default admin user '{settings.DEFAULT_ADMIN_USER}' already exists.")
    finally:
        db.close()

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(target_systems.router, prefix="/api/v1/target-systems", tags=["target-systems"])
app.include_router(certificates.router, prefix="/api/v1/certificates", tags=["certificates"])
app.include_router(logs.router, prefix="/api/v1/logs", tags=["logs"])
app.include_router(system.router, prefix="/api/v1/system", tags=["system"])
app.include_router(dns.router, prefix="/api/v1/dns", tags=["dns"])
app.include_router(deploy.router, prefix="/api/v1/deploy", tags=["deploy"])

@app.get("/")
def read_root():
    return {"message": "Welcome to CertSync"}
