from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1.responses import error, ok
from app.core import security
from app.core.database import get_db
from app.core.errors import ErrorCode
from app.models.user import User, UserSetting
from app.schemas.common import LoginRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(request: Request, body: LoginRequest, session: AsyncSession = Depends(get_db)):
    user = await session.scalar(select(User).where(User.email == body.email))
    if user is None or not user.password_hash or not security.verify_password(body.password, user.password_hash):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=401,
            content=error(request, ErrorCode.AUTH_UNAUTHORIZED.value, "Invalid credentials"),
        )
    token = security.create_access_token(user.id, extra={"name": user.name})
    return ok(
        request,
        TokenResponse(
            access_token=token,
            user=UserResponse.model_validate(user),
        ),
    )


@router.get("/me")
async def me(request: Request, user: User = Depends(get_current_user)):
    return ok(request, UserResponse.model_validate(user))


@router.get("/bootstrap")
async def bootstrap(session: AsyncSession = Depends(get_db)) -> dict:
    """Dev-only convenience endpoint that auto-creates and signs in the
    demo user so the frontend can boot without a login screen.

    Disabled unless BOTH debug mode and seed_demo_user are enabled, so it
    can never mint tokens in a production deployment."""
    from app.core.config import settings

    if not (settings.debug and settings.seed_demo_user):
        raise HTTPException(status_code=404, detail="Bootstrap disabled")
    user = await session.scalar(select(User).where(User.email == "demo@personalos.local"))
    if user is None:
        user = User(
            email="demo@personalos.local",
            name="Demo User",
            password_hash=security.hash_password("demo1234"),
            timezone="Asia/Shanghai",
            locale="zh-CN",
        )
        session.add(user)
        setting = UserSetting(user=user)
        session.add(setting)
        await session.flush()
        await session.commit()
    token = security.create_access_token(user.id, extra={"name": user.name})
    return {
        "success": True,
        "data": {
            "access_token": token,
            "user": UserResponse.model_validate(user),
        },
    }
