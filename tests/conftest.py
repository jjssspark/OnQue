import os

os.environ.setdefault("DATABASE_URL", "postgresql://unused:unused@localhost/unused")
os.environ.setdefault("JWT_SECRET", "test-secret-key-not-for-production")
os.environ.setdefault("GOOGLE_API_KEY", "test-key")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

# Create test engine with StaticPool to ensure all threads share the same in-memory database
TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# Import db first
import db

# Replace the engine in db module BEFORE importing main
# This ensures main.py uses our test engine when it runs Base.metadata.create_all()
db.engine = TEST_ENGINE

# Now import main which will use the replaced engine
from db import Base, get_db
from main import app

TestSessionLocal = sessionmaker(bind=TEST_ENGINE, autoflush=False, autocommit=False)


@pytest.fixture()
def client():
    Base.metadata.create_all(bind=TEST_ENGINE)

    def override_get_db():
        db_session = TestSessionLocal()
        try:
            yield db_session
        finally:
            db_session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=TEST_ENGINE)


@pytest.fixture()
def db_session(client):
    """Direct DB session sharing the same in-memory engine as `client`, for
    seeding rows that the HTTP API has no endpoint to create (e.g. a Todo
    inserted directly rather than extracted from a chat message)."""
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
