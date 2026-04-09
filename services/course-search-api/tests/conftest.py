from collections.abc import Generator

import pytest
from course_search_api.main import app
from fastapi.testclient import TestClient
from shared.auth import create_access_token, hash_password
from shared.database import engine, get_db
from shared.models import User
from sqlalchemy.orm import Session


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Yield a transactional session — all writes are rolled back at test end.

    Opens a dedicated connection, begins an outer transaction, and binds a
    Session to it with ``join_transaction_mode="create_savepoint"``. This
    lets the test body call ``session.commit()`` without ending the outer
    transaction — commits land on a SAVEPOINT which SQLAlchemy re-opens
    after each flush. Rolling back the outer transaction at teardown undoes
    everything the test did, including the "committed" work.

    The fixture also overrides the FastAPI ``get_db`` dependency so that
    requests made via the ``client`` fixture see the same connection — the
    app can read rows the test body inserted, and those rows disappear
    cleanly after the test finishes.

    Tests that don't need to write to the DB can keep using ``client``
    directly and will hit the real ``SessionLocal`` as before.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    def _override_get_db() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers(db_session: Session) -> dict[str, str]:
    """Create a test user and return Bearer auth headers.

    Depends on db_session so the user is visible to get_current_user via the
    overridden get_db dependency.  The user is rolled back with the session at
    test teardown.
    """
    user = User(
        email="testuser@example.com",
        password_hash=hash_password("irrelevant"),
        name="Test User",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return _auth(create_access_token(user.id))
