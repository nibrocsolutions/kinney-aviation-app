import os
import tempfile
from pathlib import Path

_root = Path(tempfile.mkdtemp(prefix="kinney-aviation-"))
os.environ["DATA_DIR"] = str(_root)
os.environ["DATABASE_URL"] = f"sqlite:///{_root / 'test.db'}"
os.environ["SEED_DEMO"] = "1"


import pytest


@pytest.fixture(autouse=True)
def fresh_database():
    import app.models  # noqa: F401
    from app.database import Base, SessionLocal, engine
    from app.seed import seed_database

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
        yield test_client
