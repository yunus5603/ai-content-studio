import os
import tempfile

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres@127.0.0.1:5432/studio_test")
os.environ["ENV"] = "test"
os.environ["AUTH_MODE"] = "dev"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["LOCAL_STORAGE_DIR"] = tempfile.mkdtemp(prefix="studio-media-")
os.environ["ENABLE_DEBUG_OPERATIONS"] = "true"

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
async def schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_tables():
    yield
    names = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {names} CASCADE"))


class Client:
    """Test client that acts as a given user (dev auth)."""

    def __init__(self, http: httpx.AsyncClient):
        self.http = http

    def as_user(self, email: str):
        http = self.http

        class _As:
            async def request(self, method, url, **kw):
                headers = {"X-Dev-User": email, **kw.pop("headers", {})}
                return await http.request(method, url, headers=headers, **kw)

            def __getattr__(self, method):
                return lambda url, **kw: self.request(method.upper(), url, **kw)

        return _As()


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield Client(http)


@pytest.fixture
def alice(client):
    return client.as_user("alice@example.com")


@pytest.fixture
def bob(client):
    return client.as_user("bob@example.com")
