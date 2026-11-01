import sqlite3
import jwt
import os

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel
from pwdlib import PasswordHash

SECRET_KEY = os.environ["LOTIA_SECRET_KEY"]
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def create_access_token(data: dict):
    to_encode = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return encoded_jwt

def decode_access_token(token: str):
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )
        return payload

    except jwt.InvalidTokenError:
        return None


security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    token = credentials.credentials

    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=401,
            detail="无效或已过期的令牌"
        )

    user_id = payload.get("sub")

    if user_id is None:
        raise HTTPException(
            status_code=401,
            detail="令牌中缺少用户信息"
        )

    conn = get_db_connection()

    try:
        user = conn.execute(
            "SELECT id, username FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
    finally:
        conn.close()

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="用户不存在"
        )

    return {
        "id": user[0],
        "username": user[1]
    }

password_hash = PasswordHash.recommended()

def hash_password(password):
    return password_hash.hash(password)

def verify_password(plain_password, hashed_password):
    return password_hash.verify(plain_password, hashed_password)

def get_db_connection():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    database_path = os.path.join(base_dir, "lotia.db")
    conn = sqlite3.connect(database_path)
    return conn
def create_table():
    conn = get_db_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "https://julian-yulijin.github.io"
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "欢迎来到洛蒂亚！"}

@app.get("/me")
def read_me(current_user: dict = Depends(get_current_user)):
    return current_user

class UserRegister(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

@app.post("/login")
def login(user: UserLogin):
    conn = get_db_connection()

    account = conn.execute(
        "SELECT * FROM users WHERE username = ?",
        (user.username,)
    ).fetchone()

    conn.close()

    if account is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if not verify_password(user.password, account[2]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    access_token = create_access_token(
        data={"sub": str(account[0])}
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@app.post("/register")
def register(user: UserRegister):
    conn = get_db_connection()

    try:
        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (user.username, hash_password(user.password))
        )

        conn.commit()

    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="用户名已存在")

    finally:
        conn.close()

    return {"message": "注册成功"}

create_table()

def add_user(username, password_hash):
    conn = get_db_connection()

    conn.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, password_hash)
    )

    conn.commit()
    conn.close()