import hashlib
from fastapi import Request

from app.core.storage import load_users, save_users


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def init_default_admin(username: str = "admin", password: str = "1234"):
    users = load_users()
    if username not in users:
        users[username] = hash_password(password)
        save_users(users)


def current_user(request: Request):
    return request.session.get("user")


def require_login(request: Request) -> bool:
    return current_user(request) is not None
