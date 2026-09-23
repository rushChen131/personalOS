from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    action,
    auth,
    chat,
    context,
    goal,
    health,
    journal,
    memory,
)
from app.api.v1.responses import setup_exception_handlers
from app.core import security
from app.core.config import settings
from app.core.database import engine
from app.core.logging import logger
from app.models import Base
from app.models.user import User, UserSetting


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    if settings.seed_demo_user:
        from sqlalchemy import select

        from app.core.database import SessionLocal

        async with SessionLocal() as session:
            existing = await session.scalar(select(User).where(User.email == "demo@personalos.local"))
            if existing is None:
                user = User(
                    email="demo@personalos.local",
                    name="Demo User",
                    password_hash=security.hash_password("demo1234"),
                    timezone="Asia/Shanghai",
                    locale="zh-CN",
                )
                session.add(user)
                session.add(UserSetting(user=user))
                await session.commit()
                logger.info("seed demo user")
            else:
                logger.info("demo user already present")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup",
                app=settings.app_name,
                version=settings.app_version,
                db=settings.database_url,
                llm_provider=settings.llm_provider)
    await init_db()
    from app.jobs.in_process import dispatcher

    await dispatcher.register()
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", settings.frontend_origin],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request.state.request_id = f"req_{uuid.uuid4().hex[:12]}"
    return await call_next(request)


setup_exception_handlers(app)

v1_prefix = "/api/v1"
app.include_router(health.router, prefix=v1_prefix)
app.include_router(action.router, prefix=v1_prefix)
app.include_router(auth.router, prefix=v1_prefix)
app.include_router(journal.router, prefix=v1_prefix)
app.include_router(goal.router, prefix=v1_prefix)
app.include_router(memory.router, prefix=v1_prefix)
app.include_router(chat.router, prefix=v1_prefix)
app.include_router(context.router, prefix=v1_prefix)
