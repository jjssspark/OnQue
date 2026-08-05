import os
from unittest.mock import patch

# Set test environment variables BEFORE any module imports
os.environ["DATABASE_URL"] = "postgresql://unused:unused@localhost/unused"
os.environ["JWT_SECRET"] = "test-secret-key-not-for-production"
os.environ["GOOGLE_API_KEY"] = "test-key"

from sqlalchemy import create_engine

# Create test engine first
TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
)

# Mock sqlalchemy.create_engine globally to return our test engine
original_create_engine = create_engine
def mock_create_engine(url, *args, **kwargs):
    """Return the SQLite test engine regardless of the URL"""
    return TEST_ENGINE

# Mock load_dotenv and create_engine to prevent it from reading the real .env file
# and to use our SQLite engine instead of creating a PostgreSQL connection
with patch("dotenv.load_dotenv"), patch("sqlalchemy.create_engine", side_effect=mock_create_engine):
    import pytest
    from sqlalchemy.orm import sessionmaker
    from fastapi.testclient import TestClient

    import db
    from db import Base, get_db
    from main import app

from sqlalchemy.orm import sessionmaker

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
