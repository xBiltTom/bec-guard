from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.database import create_session_factory
from app.models import Role, User

pytestmark = pytest.mark.integration

# Opaque storage fixture, not a password or a working authentication hash.
TEST_HASH = "test-only-opaque-hash-placeholder"


def make_user(role: Role = Role.ANALYST) -> User:
    return User(
        name="Test Analyst", email="analyst@example.test", password_hash=TEST_HASH, role=role
    )


@pytest.mark.parametrize("role", list(Role))
def test_user_is_committed_and_loaded_from_another_session(db_session, migrated_engine, role):
    user = make_user(role)
    db_session.add(user)
    db_session.commit()
    user_id = user.id

    with create_session_factory(migrated_engine)() as reader:
        loaded = reader.get(User, user_id)
        assert loaded is not None
        assert isinstance(loaded.id, UUID)
        assert loaded.id.version == 4
        assert loaded.email == "analyst@example.test"
        assert loaded.name == "Test Analyst"
        assert loaded.password_hash == TEST_HASH
        assert loaded.role is role
        assert loaded.is_active is True
        assert loaded.created_at.utcoffset() == timedelta(0)
        assert loaded.updated_at.utcoffset() == timedelta(0)
        assert loaded.created_at == loaded.updated_at


def test_duplicate_email_is_rejected_by_postgresql(db_session):
    db_session.add(make_user())
    db_session.commit()
    db_session.add(make_user(Role.ADMIN))

    with pytest.raises(IntegrityError) as error:
        db_session.commit()
    assert error.value.orig.diag.constraint_name == "uq_users_email"
    db_session.rollback()


def test_update_changes_updated_at_and_preserves_created_at(db_session):
    user = make_user()
    db_session.add(user)
    db_session.commit()
    created_at, updated_at = user.created_at, user.updated_at

    user.name = "Updated Analyst"
    user.is_active = False
    db_session.commit()
    db_session.refresh(user)

    assert user.created_at == created_at
    assert user.updated_at > updated_at
    assert user.updated_at.utcoffset() == timedelta(0)
    assert user.is_active is False


def test_database_rejects_unknown_role_even_without_orm_validation(db_session):
    with pytest.raises(IntegrityError) as error:
        db_session.execute(
            text(
                "INSERT INTO public.users (id, name, email, password_hash, role) "
                "VALUES (:id, :name, :email, :hash, :role)"
            ),
            {
                "id": uuid4(),
                "name": "Invalid Role",
                "email": "invalid@example.test",
                "hash": TEST_HASH,
                "role": "INVALID",
            },
        )
    assert error.value.orig.diag.constraint_name == "ck_users_role"
    db_session.rollback()
