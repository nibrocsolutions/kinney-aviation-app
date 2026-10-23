import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import (
    COOKIE,
    authenticate,
    clear_login_failures,
    clear_session_cookie,
    hash_password,
    login_blocked,
    record_login_failure,
    reject_missing_header,
    require_admin,
    require_user,
    revoke_sessions,
    set_session_cookie,
    start_session,
    verify_password,
)
from app.config import settings
from app.database import get_db
from app.models import AuthSession, User
from app.schemas import LoginIn, PasswordChange, UserCreate, UserOut, UserUpdate

public = APIRouter(prefix="/api")
account = APIRouter(prefix="/api", dependencies=[Depends(require_user)])
admin = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        active=user.active,
    )


def _active_admins(db: Session, excluding: int | None = None) -> int:
    query = select(func.count(User.id)).where(User.role == "admin", User.active.is_(True))
    if excluding is not None:
        query = query.where(User.id != excluding)
    return int(db.scalar(query) or 0)


@public.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


@public.post("/login", response_model=UserOut)
def login(payload: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> UserOut:
    reject_missing_header(request)
    if login_blocked(request):
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Wait a few minutes and try again.")
    password = payload.password if len(payload.password) <= 200 else ""
    user = authenticate(db, payload.username, password) if payload.username and password else None
    if user is None:
        record_login_failure(request)
        raise HTTPException(status_code=401, detail="Those credentials were not recognized.")
    clear_login_failures(request)
    token = start_session(db, user)
    db.commit()
    set_session_cookie(response, token)
    return user_out(user)


@account.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> Response:
    token = request.cookies.get(COOKIE)
    if token:
        digest = hashlib.sha256(token.encode()).hexdigest()
        row = db.scalar(select(AuthSession).where(AuthSession.token_hash == digest))
        if row is not None:
            db.delete(row)
            db.commit()
    clear_session_cookie(response)
    return Response(status_code=204)


@account.get("/me", response_model=UserOut)
def me(request: Request, db: Session = Depends(get_db)) -> UserOut:
    user = db.get(User, request.state.user.id)
    if user is None or not user.active:
        raise HTTPException(status_code=401, detail="Sign in required.")
    return user_out(user)


@account.post("/account/password")
def change_password(
    payload: PasswordChange,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    user = db.get(User, request.state.user.id)
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in required.")
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is not right.")
    if payload.new_password == payload.current_password:
        raise HTTPException(status_code=400, detail="Choose a different password.")
    if payload.new_password.lower() == user.username.lower():
        raise HTTPException(status_code=400, detail="Use a password that is not the username.")
    user.password_hash = hash_password(payload.new_password)
    revoke_sessions(db, user.id)
    db.commit()
    clear_session_cookie(response)
    return {"status": "ok", "message": "Password updated. Sign in again."}


@admin.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)) -> list[UserOut]:
    users = db.scalars(select(User).order_by(User.username))
    return [user_out(user) for user in users]


@admin.post("/users", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> UserOut:
    if payload.password.lower() == payload.username.lower():
        raise HTTPException(status_code=400, detail="Use a password that is not the username.")
    existing = db.scalar(select(User).where(User.username == payload.username))
    if existing is not None:
        raise HTTPException(status_code=409, detail="That username is already in use.")
    user = User(
        username=payload.username,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
        active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user_out(user)


@admin.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> UserOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    data = payload.model_dump(exclude_unset=True)
    password = data.pop("password", None)
    next_role = data.get("role", user.role)
    next_active = data.get("active", user.active)
    removing_admin = user.role == "admin" and user.active and not (next_role == "admin" and next_active)
    if removing_admin and _active_admins(db, excluding=user.id) == 0:
        raise HTTPException(status_code=409, detail="Keep at least one active administrator.")
    if user.id == request.state.user.id and (next_active is False or next_role != "admin"):
        raise HTTPException(status_code=409, detail="Ask another administrator to change your own access.")
    if "display_name" in data and data["display_name"] is not None:
        user.display_name = data["display_name"]
    if "role" in data and data["role"] is not None:
        user.role = data["role"]
    if "active" in data and data["active"] is not None:
        user.active = data["active"]
        if not user.active:
            revoke_sessions(db, user.id)
    signed_out = False
    if password:
        if password.lower() == user.username.lower():
            raise HTTPException(status_code=400, detail="Use a password that is not the username.")
        user.password_hash = hash_password(password)
        revoke_sessions(db, user.id)
        if user.id == request.state.user.id:
            signed_out = True
    db.commit()
    db.refresh(user)
    saved = user_out(user)
    if signed_out:
        clear_session_cookie(response)
        saved.signed_out = True
    return saved
