from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from . import crud
from .schemas.schemas import TokenData
from .core import security
from .db.database import get_db
from .db.models import User, UserRole
import logging

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = crud.crud_user.get_user_by_username(db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user

def get_optional_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """
    Returns the current user if a valid token is provided, otherwise returns None.
    Does not raise an exception for invalid or missing tokens.
    """
    token = request.headers.get("Authorization")
    if token:
        # Expecting "Bearer <token>"
        parts = token.split()
        if len(parts) == 2 and parts[0] == "Bearer":
            token = parts[1]
        else:
            return None  # Invalid format

    if not token:
        return None

    try:
        payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        
        user = crud.crud_user.get_user_by_username(db, username=username)
        return user
    except JWTError:
        return None

def require_role(role: str, allow_readonly: bool = False):
    """
    This is a more flexible role checker that understands hierarchy.
    For example, an admin can do everything a technician can.
    """
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        # Define the hierarchy of roles
        role_hierarchy = {
            UserRole.admin: 3,
            UserRole.technician: 2,
            UserRole.readonly: 1
        }
        
        required_level = role_hierarchy.get(UserRole[role], 0)
        user_level = role_hierarchy.get(current_user.role, 0)

        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires at least '{role}' privileges."
            )
        
        if not allow_readonly and current_user.role == UserRole.readonly:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Read-only users cannot perform this action."
            )
            
        return current_user
    return role_checker

# NEW: Permission helper functions for proper role hierarchy

def require_admin_only(current_user: User = Depends(get_current_user)) -> User:
    """Only admin users can access this endpoint"""
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user

def require_admin_or_technician(current_user: User = Depends(get_current_user)) -> User:
    """Admin and technician users can access this endpoint"""
    if current_user.role not in [UserRole.admin, UserRole.technician]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or technician privileges required"
        )
    return current_user

def require_any_authenticated(current_user: User = Depends(get_current_user)) -> User:
    """Any authenticated user (admin, technician, readonly) can access this endpoint"""
    if current_user.role not in [UserRole.admin, UserRole.technician, UserRole.readonly]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authentication required"
        )
    return current_user

def get_current_user_sse(request: Request, db: Session = Depends(get_db)) -> User:
    """
    SSE-specific user authentication that extracts token from query parameters.
    Uses the SAME logic as get_current_user for consistency.
    """
    logger.info("SSE authentication started")
    
    # Extract token from query parameters
    token = request.query_params.get("token")
    logger.info(f"Token extracted from query: {bool(token)}")
    
    if not token:
        logger.error("No token found in SSE request query parameters")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated - no token provided",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Use EXACTLY the same authentication logic as get_current_user
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        logger.info("Attempting to decode JWT token")
        payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
        username: str = payload.get("sub")
        logger.info(f"JWT decode successful, username: {username}")
        
        if username is None:
            logger.error("No 'sub' field in JWT payload")
            raise credentials_exception
            
        token_data = TokenData(username=username)
        
    except JWTError as e:
        logger.error(f"JWT decode failed: {str(e)}")
        raise credentials_exception
    
    # Look up user in database
    logger.info(f"Looking up user in database: {token_data.username}")
    user = crud.crud_user.get_user_by_username(db, username=token_data.username)
    
    if user is None:
        logger.error(f"User not found in database: {token_data.username}")
        raise credentials_exception
    
    logger.info(f"SSE authentication successful for user: {user.username} (role: {user.role})")
    return user
