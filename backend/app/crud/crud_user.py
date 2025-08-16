import logging
from sqlalchemy.orm import Session
from ..db import models
from ..schemas import schemas
from passlib.context import CryptContext

logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_user_by_username(db: Session, username: str):
    logger.debug(f"Querying for user by username: {username}")
    user = db.query(models.User).filter(models.User.username == username).first()
    if user:
        logger.debug(f"User '{username}' found.")
    else:
        logger.debug(f"User '{username}' not found.")
    return user

def create_user(db: Session, user: schemas.UserCreate):
    logger.debug(f"Creating new user with username: {user.username}")
    hashed_password = pwd_context.hash(user.password)
    db_user = models.User(
        username=user.username,
        hashed_password=hashed_password,
        role=user.role
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    logger.info(f"User '{user.username}' created successfully.")
    return db_user

def verify_password(plain_password: str, hashed_password: str) -> bool:
    logger.debug("Verifying password.")
    is_verified = pwd_context.verify(plain_password, hashed_password)
    if is_verified:
        logger.debug("Password verification successful.")
    else:
        logger.debug("Password verification failed.")
    return is_verified

def get_users(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.User).offset(skip).limit(limit).all()

def update_user(db: Session, user_id: int, user_update: schemas.UserCreate):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user:
        db_user.username = user_update.username
        db_user.role = user_update.role
        if user_update.password:
            db_user.hashed_password = pwd_context.hash(user_update.password)
        db.commit()
        db.refresh(db_user)
    return db_user

def update_password(db: Session, user_id: int, new_password: str):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user:
        db_user.hashed_password = pwd_context.hash(new_password)
        db.commit()
        db.refresh(db_user)
    return db_user

def delete_user(db: Session, user_id: int):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user:
        db.delete(db_user)
        db.commit()
    return db_user
