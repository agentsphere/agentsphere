
from app.models.models import User
import os
import requests

from fastapi import HTTPException, Header, Depends, status
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext

from pydantic import BaseModel, Field
from config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
import logging
logger= logging.getLogger(__name__)


def introspect_token(token: str) -> dict:
    if token is None: 
       raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token introspection failed"
        ) 
    ctoken = token.split(" ", 1)[1] if token.startswith("Bearer ") else token
    introspection_url = "https://auth.agentsphere.cloud/realms/agentsphere/protocol/openid-connect/token/introspect"

    client_id = os.getenv("CLIENT")
    client_secret = os.getenv("CLIENT_SECRET")

    logger.debug(f"id {client_id} sec {client_secret}")
    response = requests.post(
        introspection_url,
        headers={"Content-Type":"application/x-www-form-urlencoded"},
        data={"token": ctoken, "client_id": client_id, "client_secret": client_secret}
    )
    if response.status_code == 200:
        return response.json()
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token introspection failed"
        )





def get_user_headers(
    user_id: Optional[str] = Header(None, alias="X-OpenWebUI-User-Id"),
    user_role: Optional[str] = Header(None, alias="X-OpenWebUI-User-Role"),
    user_name: Optional[str] = Header(None, alias="X-OpenWebUI-User-Name"),
    user_email: Optional[str] = Header(None, alias="X-OpenWebUI-User-Email"),
    token: Optional[str] = Header(None, alias="Authorization")
):
    return {
        "id": user_id,
        "role": user_role,
        "username": user_name,
        "mail": user_email,
        "token": token
    }


def get_user(user_headers: dict = Depends(get_user_headers)):
    introspect_token(user_headers.get("token", None))
    return User(**user_headers)

def validate_token(token_header: dict = Depends(get_user_headers)):
    introspect_token(token_header.get("token", None))
    return



def get_user(user_headers: dict = Depends(get_user_headers)):
    introspect_token(user_headers.get("token", None))
    return User(**user_headers)

# Password hashing utility
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_access_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        payload["token"] = token
        return payload  # Returns user data if token is valid
    except JWTError:
        return None
    
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_current_user_none(token: str = Depends(oauth2_scheme)):
    return verify_access_token(token)


def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = verify_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return payload  # This returns the user data from the token

from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel
from datetime import timedelta

from auth import create_access_token, hash_password, verify_password


router = APIRouter()


# Dummy user database
fake_users_db = {
    "testuser": {
        "username": "testuser",
        "password": hash_password("password123"),  # Hashed password
    }
}

fake_executioner_clientId = {}

def get_first_uuid_for_user(user):
    clients = fake_executioner_clientId.get(user,None)
    if clients is None: return None
    return clients[0]

def add_executioner(uuid: str, user_id: str):
    # Ensure the user has a token list in fake_executioner_token
    if user_id not in fake_executioner_clientId:
        fake_executioner_clientId[user_id] = []

    # Avoid duplicate tokens
    if uuid not in fake_executioner_clientId[user_id]:
        fake_executioner_clientId[user_id].append(uuid)

    return create_access_token(data={"user_id": user_id, "uuid": uuid}, expires_delta=timedelta(days=100))

def check_executioner_uuid_for_user(user, uuid):
    if not uuid in fake_executioner_clientId[user]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Executioner {token} doesn't belong to User {user}" )
    return

def check_executioner(token):
    user = get_current_user_none(token)
    if user is None:
        logger.debug("user not found")
        return False
    
    if fake_executioner_clientId.get(user["user_id"], None) is None:
       fake_executioner_clientId[user["user_id"]] = []
    
    if user["uuid"] not in fake_executioner_clientId[user["user_id"]]:

        fake_executioner_clientId[user["user_id"]].append(user["uuid"])

        logger.debug("uuid not in exec clients, added")
        #return False

    return True
 
def get_uuid(token):
    user = get_current_user_none(token)
    if user is None:
        logger.debug("user not found")
        return None
    return user.get("uuid", None) 

class UserLogin(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str

@router.post("/token", response_model=TokenResponse)
def login_for_access_token(user_data: UserLogin):
    user = fake_users_db.get(user_data.username)
    if not user or not verify_password(user_data.password, user["password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access_token = create_access_token(data={"sub": user_data.username}, expires_delta=timedelta(minutes=30))
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/users/me")
def read_users_me(current_user: dict = Depends(get_current_user)):
    print(current_user)
    return {"username": current_user["sub"]}
