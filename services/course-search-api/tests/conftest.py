from collections.abc import Generator

import pytest
from course_search_api.main import app
from fastapi.testclient import TestClient
from shared.database import SessionLocal
from sqlalchemy.orm import Session


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Yield a real database session and roll back after each test."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()
