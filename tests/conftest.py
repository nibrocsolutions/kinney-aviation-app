import os
import tempfile
from pathlib import Path

_root = Path(tempfile.mkdtemp(prefix="kinney-aviation-"))
os.environ["DATA_DIR"] = str(_root)
os.environ["DATABASE_URL"] = f"sqlite:///{_root / 'test.db'}"
os.environ["SEED_DEMO"] = "1"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "test-admin-password"
os.environ["SHOP_USERNAME"] = "ron"
os.environ["SHOP_PASSWORD"] = "test-shop-password"
os.environ["SESSION_SECURE"] = "0"


import pytest


@pytest.fixture(autouse=True)
def fresh_database():
    import app.models  # noqa: F401
    from app.database import Base, SessionLocal, engine
    from app.seed import seed_database

    from app.auth import reset_login_limits

    reset_login_limits()
    engine.dispose()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()


@pytest.fixture
def client(fresh_database):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        test_client.headers["X-Kinney-Request"] = "1"
        signed_in = test_client.post(
            "/api/login",
            json={"username": "admin", "password": "test-admin-password"},
        )
        assert signed_in.status_code == 200, signed_in.text
        yield test_client


@pytest.fixture
def anon(fresh_database):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
