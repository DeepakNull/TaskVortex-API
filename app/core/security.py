import bcrypt 
from datetime import datetime, timedelta, timezone
import os
from dotenv import load_dotenv
from jose import jwt
from app.core.config import settings

def hash_password(password: str) -> str:
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(password_bytes, salt)
    return hashed_bytes.decode('utf-8')
 
def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_bytes = plain_password.encode('utf-8')
    if len(password_bytes) > 72:
        return False 
    return bcrypt.checkpw(password_bytes, hashed_password.encode('utf-8'))
    # Securely compare them using constant-time verification against timing attacks
    
DUMMY_HASH = hash_password("not-a-real-password")

def create_access_token(data:dict)-> str:
    SECRET_KEY = settings.SECRET_KEY
    ALGORITHM = settings.ALGORITHM
    ACCESS_TOKEN_EXPIRE_MINUTES = int(settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = data.copy() 
    
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM
    )
    
    return encoded_jwt