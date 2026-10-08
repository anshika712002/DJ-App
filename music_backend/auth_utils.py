from passlib.context import CryptContext
import jwt
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import uuid
import logging

REFRESH_TOKEN_EXPIRE_DAYS = 90

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY", "mysecret")

if SECRET_KEY == "mysecret":
    logger.warning("Using default SECRET_KEY ")

if not SECRET_KEY:
    raise ValueError("❌ SECRET_KEY is missing.")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 720  #min

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    to_encode["tokenType"] = "access"
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str):
    try:
        if token.startswith("Bearer "):
            token = token.split("Bearer ", 1)[1]

        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        logger.debug("Access token decoded (userId=%s, role=%s)", payload.get("userId"), payload.get("role"))
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Access token expired")
        return None
    except jwt.DecodeError:
        logger.warning("JWT decode failed (malformed token)")
        return None

def create_refresh_token(data: dict):
    to_encode = data.copy()
    to_encode["tokenType"] = "refresh"
    to_encode["jti"] = str(uuid.uuid4())
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    # to_encode.update({"exp": expire})
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
