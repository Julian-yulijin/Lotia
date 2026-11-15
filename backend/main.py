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
            "SELECT id, username, is_admin FROM users WHERE id = ?",
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
    "username": user[1],
    "is_admin": user[2]
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
    conn.execute("PRAGMA foreign_keys = ON")

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

class StoryCreate(BaseModel):
    title: str
    content: str
    location_ids: list[int] = []
    period_ids: list[int] = []

class StoryUpdate(BaseModel):
    title: str
    content: str
    location_ids: list[int] = []
    period_ids: list[int] = []

class ReviewReject(BaseModel):
    comment: str

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



@app.post("/stories")
def create_story(
    story: StoryCreate,
    current_user: dict = Depends(get_current_user)
):
    conn = get_db_connection()

    try:
        # 1. 检查地点 ID 是否重复
        if len(story.location_ids) != len(set(story.location_ids)):
            raise HTTPException(
                status_code=400,
                detail="不能重复选择同一个地点"
            )

        # 2. 检查历史时期 ID 是否重复
        if len(story.period_ids) != len(set(story.period_ids)):
            raise HTTPException(
                status_code=400,
                detail="不能重复选择同一个历史时期"
            )

        # 3. 检查所有地点是否存在
        if story.location_ids:
            placeholders = ",".join(
                "?" for _ in story.location_ids
            )

            locations = conn.execute(
                f"""
                SELECT id FROM locations
                WHERE id IN ({placeholders})
                """,
                story.location_ids
            ).fetchall()

            if len(locations) != len(story.location_ids):
                raise HTTPException(
                    status_code=400,
                    detail="选择的地点中存在无效 ID"
                )

        # 4. 检查所有历史时期是否存在
        if story.period_ids:
            placeholders = ",".join(
                "?" for _ in story.period_ids
            )

            periods = conn.execute(
                f"""
                SELECT id FROM historical_periods
                WHERE id IN ({placeholders})
                """,
                story.period_ids
            ).fetchall()

            if len(periods) != len(story.period_ids):
                raise HTTPException(
                    status_code=400,
                    detail="选择的历史时期中存在无效 ID"
                )

        # 5. 创建故事主体
        cursor = conn.execute(
            """
            INSERT INTO stories (author_id)
            VALUES (?)
            """,
            (current_user["id"],)
        )

        story_id = cursor.lastrowid

        # 6. 创建第一个故事版本
        cursor = conn.execute(
            """
            INSERT INTO story_versions (
                story_id,
                version_number,
                title,
                content,
                editor_id,
                status
            )
            VALUES (?, 1, ?, ?, ?, 'pending')
            """,
            (
                story_id,
                story.title,
                story.content,
                current_user["id"]
            )
        )

        version_id = cursor.lastrowid

        # 7. 建立故事版本与地点的关联
        for location_id in story.location_ids:
            conn.execute(
                """
                INSERT INTO story_version_locations (
                    version_id,
                    location_id
                )
                VALUES (?, ?)
                """,
                (version_id, location_id)
            )

        # 8. 建立故事版本与历史时期的关联
        for period_id in story.period_ids:
            conn.execute(
                """
                INSERT INTO story_version_periods (
                    version_id,
                    period_id
                )
                VALUES (?, ?)
                """,
                (version_id, period_id)
            )

        # 9. 提交事务
        conn.commit()

        return {
            "message": "故事投稿成功，等待审核",
            "story_id": story_id,
            "version_id": version_id,
            "status": "pending",
            "location_ids": story.location_ids,
            "period_ids": story.period_ids
        }

    except sqlite3.Error:
        conn.rollback()
        raise HTTPException(
            status_code=500,
            detail="故事投稿失败"
        )

    finally:
        conn.close()


@app.get("/stories")
def read_stories():
    conn = get_db_connection()

    try:
        stories = conn.execute(
            """
            SELECT
                stories.id,
                story_versions.id,
                story_versions.title,
                story_versions.content
            FROM stories
            JOIN story_versions
                ON stories.published_version_id = story_versions.id
            WHERE
                stories.is_deleted = 0
                AND stories.published_version_id IS NOT NULL
            """
        ).fetchall()

        return [
            {
                "story_id": row[0],
                "version_id": row[1],
                "title": row[2],
                "content": row[3]
            }
            for row in stories
        ]

    finally:
        conn.close()

@app.get("/my-stories")
def read_my_stories(
    current_user: dict = Depends(get_current_user)
):
    conn = get_db_connection()

    try:
        stories = conn.execute(
            """
            SELECT
                stories.id,
                story_versions.id,
                story_versions.version_number,
                story_versions.title,
                story_versions.content,
                story_versions.status,
                story_versions.created_at
            FROM stories
            JOIN story_versions
                ON stories.id = story_versions.story_id
            WHERE stories.author_id = ?
            ORDER BY stories.id, story_versions.version_number
            """,
            (current_user["id"],)
        ).fetchall()

        return [
            {
                "story_id": row[0],
                "version_id": row[1],
                "version_number": row[2],
                "title": row[3],
                "content": row[4],
                "status": row[5],
                "created_at": row[6]
            }
            for row in stories
        ]

    finally:
        conn.close()

@app.get("/my-stories/{story_id}/history")
def get_story_history(
    story_id: int,
    current_user: dict = Depends(get_current_user)
):
    conn = get_db_connection()

    try:
        story = conn.execute(
            """
            SELECT author_id
            FROM stories
            WHERE id = ?
            """,
            (story_id,)
        ).fetchone()

        if story is None:
            raise HTTPException(
                status_code=404,
                detail="故事不存在"
            )

        if (
            story[0] != current_user["id"]
            and not current_user["is_admin"]
        ):
            raise HTTPException(
                status_code=403,
                detail="无权查看该故事"
            )

        versions = conn.execute(
            """
            SELECT
                sv.id,
                sv.version_number,
                sv.title,
                sv.content,
                sv.status,
                sv.created_at,
                u.username
            FROM story_versions sv
            JOIN users u ON sv.editor_id = u.id
            WHERE sv.story_id = ?
            ORDER BY sv.version_number
            """,
            (story_id,)
        ).fetchall()

        result = []

        for version in versions:
            reviews = conn.execute(
                """
                SELECT
                    r.result,
                    r.comment,
                    r.reviewed_at,
                    u.username
                FROM reviews r
                JOIN users u ON r.reviewer_id = u.id
                WHERE r.version_id = ?
                ORDER BY r.reviewed_at
                """,
                (version[0],)
            ).fetchall()

            result.append({
                "version_id": version[0],
                "version_number": version[1],
                "title": version[2],
                "content": version[3],
                "status": version[4],
                "created_at": version[5],
                "editor": version[6],
                "reviews": [
                    {
                        "result": review[0],
                        "comment": review[1],
                        "reviewed_at": review[2],
                        "reviewer": review[3]
                    }
                    for review in reviews
                ]
            })

        return {
            "story_id": story_id,
            "versions": result
        }

    finally:
        conn.close()

@app.get("/admin/pending-stories")
def read_pending_stories(
    current_user: dict = Depends(get_current_user)
):
    if current_user["is_admin"] != 1:
        raise HTTPException(
            status_code=403,
            detail="没有管理员权限"
        )

    conn = get_db_connection()

    try:
        stories = conn.execute(
            """
            SELECT
                stories.id,
                story_versions.id,
                story_versions.version_number,
                story_versions.title,
                story_versions.content,
                users.username,
                story_versions.created_at
            FROM story_versions
            JOIN stories
                ON story_versions.story_id = stories.id
            JOIN users
                ON stories.author_id = users.id
            WHERE
                story_versions.status = 'pending'
                AND stories.is_deleted = 0
            ORDER BY story_versions.created_at
            """
        ).fetchall()

        return [
            {
                "story_id": row[0],
                "version_id": row[1],
                "version_number": row[2],
                "title": row[3],
                "content": row[4],
                "author": row[5],
                "created_at": row[6]
            }
            for row in stories
        ]

    finally:
        conn.close()

@app.post("/admin/reviews/{version_id}/approve")
def approve_story(
    version_id: int,
    current_user: dict = Depends(get_current_user)
):
    if current_user["is_admin"] != 1:
        raise HTTPException(
            status_code=403,
            detail="没有管理员权限"
        )

    conn = get_db_connection()

    try:
        version = conn.execute(
            """
            SELECT story_id, status
            FROM story_versions
            WHERE id = ?
            """,
            (version_id,)
        ).fetchone()

        if version is None:
            raise HTTPException(
                status_code=404,
                detail="故事版本不存在"
            )

        if version[1] != "pending":
            raise HTTPException(
                status_code=400,
                detail="该版本不处于待审核状态"
            )

        story_id = version[0]

        conn.execute(
            """
            UPDATE story_versions
            SET status = 'approved'
            WHERE id = ?
            """,
            (version_id,)
        )

        conn.execute(
            """
            INSERT INTO reviews (
                version_id,
                reviewer_id,
                result
            )
            VALUES (?, ?, 'approved')
            """,
            (
                version_id,
                current_user["id"]
            )
        )

        conn.execute(
    """
    UPDATE stories
    SET published_version_id = ?
    WHERE id = ?
    AND (
        published_version_id IS NULL
        OR (
            SELECT version_number
            FROM story_versions
            WHERE id = stories.published_version_id
        ) < (
            SELECT version_number
            FROM story_versions
            WHERE id = ?
        )
    )
    """,
    (version_id, story_id, version_id)
)

        conn.commit()

        return {
            "message": "故事审核通过，现已公开",
            "story_id": story_id,
            "version_id": version_id,
            "status": "approved"
        }

    except sqlite3.Error:
        conn.rollback()
        raise HTTPException(
            status_code=500,
            detail="审核操作失败"
        )

    finally:
        conn.close()


@app.post("/admin/reviews/{version_id}/reject")
def reject_story(
    version_id: int,
    review: ReviewReject,
    current_user: dict = Depends(get_current_user)
):
    if current_user["is_admin"] != 1:
        raise HTTPException(
            status_code=403,
            detail="没有管理员权限"
        )

    conn = get_db_connection()

    try:
        version = conn.execute(
            """
            SELECT status
            FROM story_versions
            WHERE id = ?
            """,
            (version_id,)
        ).fetchone()

        if version is None:
            raise HTTPException(
                status_code=404,
                detail="故事版本不存在"
            )

        if version[0] != "pending":
            raise HTTPException(
                status_code=400,
                detail="该版本不处于待审核状态"
            )

        conn.execute(
            """
            UPDATE story_versions
            SET status = 'rejected'
            WHERE id = ?
            """,
            (version_id,)
        )

        conn.execute(
            """
            INSERT INTO reviews (
                version_id,
                reviewer_id,
                result,
                comment
            )
            VALUES (?, ?, 'rejected', ?)
            """,
            (
                version_id,
                current_user["id"],
                review.comment
            )
        )

        conn.commit()

        return {
            "message": "故事审核未通过",
            "version_id": version_id,
            "status": "rejected",
            "comment": review.comment
        }

    except sqlite3.Error:
        conn.rollback()
        raise HTTPException(
            status_code=500,
            detail="审核操作失败"
        )

    finally:
        conn.close()


@app.post("/stories/{story_id}/versions")
def create_story_version(
    story_id: int,
    story: StoryUpdate,
    current_user: dict = Depends(get_current_user)
):
    conn = get_db_connection()

    try:
        # 1. 检查故事是否存在，以及是否属于当前用户
        existing_story = conn.execute(
            """
            SELECT id
            FROM stories
            WHERE id = ? AND author_id = ? AND is_deleted = 0
            """,
            (story_id, current_user["id"])
        ).fetchone()

        if existing_story is None:
            raise HTTPException(
                status_code=404,
                detail="故事不存在或无权修改"
            )

        # 2. 检查地点 ID 是否重复
        if len(story.location_ids) != len(set(story.location_ids)):
            raise HTTPException(
                status_code=400,
                detail="不能重复选择同一个地点"
            )

        # 3. 检查历史时期 ID 是否重复
        if len(story.period_ids) != len(set(story.period_ids)):
            raise HTTPException(
                status_code=400,
                detail="不能重复选择同一个历史时期"
            )

        # 4. 检查所有地点是否存在
        if story.location_ids:
            placeholders = ",".join(
                "?" for _ in story.location_ids
            )

            locations = conn.execute(
                f"""
                SELECT id FROM locations
                WHERE id IN ({placeholders})
                """,
                story.location_ids
            ).fetchall()

            if len(locations) != len(story.location_ids):
                raise HTTPException(
                    status_code=400,
                    detail="选择的地点中存在无效 ID"
                )

        # 5. 检查所有历史时期是否存在
        if story.period_ids:
            placeholders = ",".join(
                "?" for _ in story.period_ids
            )

            periods = conn.execute(
                f"""
                SELECT id FROM historical_periods
                WHERE id IN ({placeholders})
                """,
                story.period_ids
            ).fetchall()

            if len(periods) != len(story.period_ids):
                raise HTTPException(
                    status_code=400,
                    detail="选择的历史时期中存在无效 ID"
                )

        # 6. 查询该故事目前最大的版本号
        result = conn.execute(
            """
            SELECT MAX(version_number)
            FROM story_versions
            WHERE story_id = ?
            """,
            (story_id,)
        ).fetchone()

        new_version_number = (result[0] or 0) + 1

        # 7. 创建新的待审核版本
        cursor = conn.execute(
            """
            INSERT INTO story_versions (
                story_id,
                version_number,
                title,
                content,
                editor_id,
                status
            )
            VALUES (?, ?, ?, ?, ?, 'pending')
            """,
            (
                story_id,
                new_version_number,
                story.title,
                story.content,
                current_user["id"]
            )
        )

        new_version_id = cursor.lastrowid

        # 8. 建立新版本与地点的关联
        for location_id in story.location_ids:
            conn.execute(
                """
                INSERT INTO story_version_locations (
                    version_id,
                    location_id
                )
                VALUES (?, ?)
                """,
                (new_version_id, location_id)
            )

        # 9. 建立新版本与历史时期的关联
        for period_id in story.period_ids:
            conn.execute(
                """
                INSERT INTO story_version_periods (
                    version_id,
                    period_id
                )
                VALUES (?, ?)
                """,
                (new_version_id, period_id)
            )

        # 10. 提交事务
        conn.commit()

        return {
            "message": "新版本创建成功，已提交审核",
            "story_id": story_id,
            "version_id": new_version_id,
            "version_number": new_version_number,
            "status": "pending",
            "location_ids": story.location_ids,
            "period_ids": story.period_ids
        }

    except sqlite3.Error:
        conn.rollback()
        raise HTTPException(
            status_code=500,
            detail="创建新版本失败"
        )

    finally:
        conn.close()


create_table()

def add_user(username, password_hash):
    conn = get_db_connection()

    conn.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, password_hash)
    )

    conn.commit()
    conn.close()