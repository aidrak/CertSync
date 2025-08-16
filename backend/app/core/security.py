from cryptography.fernet import Fernet
from .config import settings
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from pydantic import BaseModel

# Initialize Fernet with the encryption key from settings
fernet = Fernet(settings.ENCRYPTION_KEY.encode())

SECRET_KEY = settings.ENCRYPTION_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def encrypt_secret(secret: str) -> str:
    """Encrypt a secret using Fernet."""
    return fernet.encrypt(secret.encode()).decode()

def decrypt_secret(encrypted_secret: str) -> str:
    """Decrypt a secret using Fernet."""
    return fernet.decrypt(encrypted_secret.encode()).decode()

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    # Ensure 'role' is in the data to be encoded
    if 'role' not in to_encode:
        # This is a fallback, ideally the role should always be passed in
        to_encode['role'] = 'readonly' 
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

class PasswordUpdate(BaseModel):
    current_password: str
    new_password: str

def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
