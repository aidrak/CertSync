import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from ..crud import crud_user
from ..schemas.schemas import Token, User as UserSchema, UserCreate
from ..core import security
from ..db.database import get_db
from ..dependencies import get_current_user, require_admin_only, require_admin_or_technician
from ..db.models import UserRole, User
from datetime import timedelta
from typing import List

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/token", response_model=Token)
async def login_for_access_token(db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    logger.info(f"Login attempt for user: '{form_data.username}' with password: '{form_data.password}'")
    user = crud_user.get_user_by_username(db, username=form_data.username)
    if not user:
        logger.error(f"User '{form_data.username}' not found in the database.")
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.info(f"User '{form_data.username}' found. Verifying password.")
    if not crud_user.verify_password(form_data.password, user.hashed_password):
        logger.error(f"Password verification failed for user '{form_data.username}'.")
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.info(f"User '{form_data.username}' authenticated successfully. Creating access token.")
    access_token_expires = timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": user.username, "role": user.role.value}, expires_delta=access_token_expires
    )
    logger.info(f"Access token created for user: '{form_data.username}'.")
    return {"access_token": access_token, "token_type": "bearer"}

# ADMIN ONLY: Only admins can create users
@router.post("/users/", response_model=UserSchema)
def create_user(user: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin_only)):
    db_user = crud_user.get_user_by_username(db, username=user.username)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    return crud_user.create_user(db=db, user=user)

# ADMIN ONLY: Can view users
@router.get("/users/", response_model=List[UserSchema])
def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: User = Depends(require_admin_only)):
    users = crud_user.get_users(db, skip=skip, limit=limit)
    return users

@router.get("/users/me", response_model=UserSchema)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.put("/users/{user_id}", response_model=UserSchema)
def update_user_info(user_id: int, user_update: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin_only)):
    return crud_user.update_user(db=db, user_id=user_id, user_update=user_update)

@router.put("/users/{user_id}/password")
def update_user_password_by_admin(user_id: int, password_update: security.PasswordUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_admin_only)):
    crud_user.update_password(db=db, user_id=user_id, new_password=password_update.password)
    return {"message": "Password updated successfully"}

@router.put("/users/me/password")
def update_current_user_password(password_update: security.PasswordUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not crud_user.verify_password(password_update.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect current password")
    crud_user.update_password(db=db, user_id=current_user.id, new_password=password_update.new_password)
    return {"message": "Password updated successfully"}

@router.delete("/users/{user_id}", status_code=204)
def delete_user_by_admin(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin_only)):
    crud_user.delete_user(db=db, user_id=user_id)
    return
