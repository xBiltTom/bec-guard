from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import DateTime, inspect, text

pytestmark = pytest.mark.integration


def test_upgrade_downgrade_upgrade_and_metadata_match(migrated_engine, migration_runner):
    def tables():
        return set(inspect(migrated_engine).get_table_names(schema="public"))

    # The session fixture already applied upgrade head to the clean test database.
    assert tables() == {"users", "audit_log", "alembic_version"}
    with migrated_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM public.alembic_version")) == (
            "0003_create_audit_log"
        )

    migration_runner(command.downgrade, "0001_create_users")
    assert tables() == {"users", "alembic_version"}
    with migrated_engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT to_regprocedure('public.reject_audit_log_mutation()')"))
            is None
        )
    migration_runner(command.upgrade, "head")
    migration_runner(command.downgrade, "base")
    assert tables() == {"alembic_version"}
    with migrated_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM public.alembic_version")) == 0

    migration_runner(command.upgrade, "head")
    assert tables() == {"users", "audit_log", "alembic_version"}
    inspector = inspect(migrated_engine)
    columns = inspector.get_columns("users", schema="public")
    assert {column["name"] for column in columns} == {
        "id",
        "name",
        "email",
        "password_hash",
        "role",
        "is_active",
        "created_at",
        "updated_at",
    }
    assert all(column["nullable"] is False for column in columns)
    for column in columns:
        if column["name"] in {"created_at", "updated_at"}:
            assert isinstance(column["type"], DateTime)
            assert column["type"].timezone is True
    indexes = inspector.get_indexes("users", schema="public")
    assert len(indexes) == 1  # Only the functional UNIQUE index; no redundant email index.
    assert indexes[0]["name"] == "uq_users_email_lower"
    assert indexes[0]["unique"] is True
    assert indexes[0]["expressions"] == ["lower(email::text)"]
    migration_runner(command.check)


def test_identity_migration_rejects_collisions_without_merging(migrated_engine, migration_runner):
    migration_runner(command.downgrade, "0001_create_users")
    try:
        with migrated_engine.begin() as connection:
            for email in ["admin@example.com", " ADMIN@EXAMPLE.COM "]:
                connection.execute(
                    text(
                        "INSERT INTO public.users (id, name, email, password_hash, role) "
                        "VALUES (:id, 'Collision fixture', :email, 'opaque-test-marker', 'ADMIN')"
                    ),
                    {"id": uuid4(), "email": email},
                )
        with pytest.raises(RuntimeError, match="normalization collision"):
            migration_runner(command.upgrade, "head")
        with migrated_engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM public.users")) == 2
            assert connection.scalar(text("SELECT version_num FROM public.alembic_version")) == (
                "0001_create_users"
            )
    finally:
        with migrated_engine.begin() as connection:
            connection.execute(text("DELETE FROM public.users"))
        migration_runner(command.upgrade, "head")
