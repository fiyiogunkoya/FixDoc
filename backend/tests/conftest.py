"""Shared pytest fixtures.

Backend tests run against an in-memory SQLite database with the full
SQLAlchemy schema created via `Base.metadata.create_all`. Alembic is tested
separately against a real Postgres instance in CI.
"""
import os
import uuid
from typing import Generator, Optional

import pytest
from fastapi import Query
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("FIXDOC_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FIXDOC_CLERK_JWKS_URL", "https://example.test/.well-known/jwks.json")

from app.database import Base, get_db  # noqa: E402
from app.dependencies import RequestContext, get_request_context  # noqa: E402
from app.main import create_app  # noqa: E402
from app.middleware.auth import get_current_user  # noqa: E402
from app.models.team import TeamMember  # noqa: E402
from app.models.user import User  # noqa: E402


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine) -> Generator[Session, None, None]:
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_user(db: Session) -> User:
    user = User(clerk_user_id="user_test", email="test@example.com", display_name="Test User")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def client(db, test_user) -> TestClient:
    app = create_app()

    def _override_db():
        yield db

    def _override_user():
        return test_user

    def _override_ctx(team_id: Optional[uuid.UUID] = Query(None)) -> RequestContext:
        if team_id is None:
            from fastapi import HTTPException, status

            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "team_id query parameter required"
            )
        # Ensure membership (Clerk path parity)
        member = (
            db.query(TeamMember)
            .filter(TeamMember.team_id == team_id, TeamMember.user_id == test_user.id)
            .one_or_none()
        )
        if member is None:
            from fastapi import HTTPException, status

            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this team")
        return RequestContext(team_id=team_id, user_id=test_user.id, auth_method="clerk")

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_request_context] = _override_ctx

    return TestClient(app)
