"""
Pytest configuration for backend tests.
Provides dependency overrides for auth and an isolated test database so tests run completely offline and sandboxed.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import app.models  # ensure models are registered on Base.metadata
from app.auth import AuthenticatedUser, get_current_user
from app.database import Base, get_db
from app.main import app

# Static pool in-memory SQLite so tables persist across connections in tests
from sqlalchemy.pool import StaticPool
TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)
Base.metadata.create_all(bind=TEST_ENGINE)


@pytest.fixture(autouse=True)
def override_auth_and_db_for_tests():
    """Mock auth and provide isolated in-memory DB for all tests."""
    mock_user = AuthenticatedUser("test-user-id", "test@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    def _get_test_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_test_db
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)
