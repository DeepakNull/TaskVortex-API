import os

# Must run before any app import so Settings picks these up (env vars beat .env files).
os.environ["REDIS_URL"] = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/1")
os.environ["RATE_LIMIT_CAPACITY"] = "100000"
os.environ["RATE_LIMIT_REFILL_RATE"] = "100000"
os.environ["RATE_LIMIT_TTL"] = "60"

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy import text

from app.core.config import settings
from app.core.database import get_db
from app.core.redis import redis_client
from app.main import app
from app.models.base import Base

assert settings.TEST_DATABASE_URL, "TEST_DATABASE_URL is not set"
test_engine = create_async_engine(settings.TEST_DATABASE_URL, echo=False, poolclass=NullPool)


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def prepare_schema():
    assert "test" in test_engine.url.database, "Refusing to run against a non-test database"
    async with test_engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)


@pytest_asyncio.fixture(autouse=True)
async def clean_redis():
    db = redis_client.connection_pool.connection_kwargs.get("db")
    assert db not in (None, 0), "Refusing to flush Redis db 0"
    await redis_client.flushdb()
    yield


@pytest_asyncio.fixture
async def db_connection():
    async with test_engine.connect() as connection:
        yield connection


@pytest_asyncio.fixture
async def db_transaction(db_connection):
    transaction = await db_connection.begin()
    yield db_connection
    await transaction.rollback()


@pytest_asyncio.fixture
async def db_session(db_transaction):
    session = AsyncSession(
        bind=db_transaction,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    yield session
    await session.close()


@pytest_asyncio.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def mock_publish(monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr("app.services.task_service.publish_message", mock)
    return mock


@pytest_asyncio.fixture
async def make_headers(client):
    async def _make(email="alex@gmail.com"):
        payload = {"name": "alex", "email": email, "password": "alexPassword123"}
        r = await client.post("/api/v1/users/signup", json=payload)
        assert r.status_code == 201
        r = await client.post(
            "/api/v1/users/login",
            data={"username": email, "password": payload["password"]},
        )
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _make


@pytest_asyncio.fixture
async def auth_headers(make_headers):
    return await make_headers()