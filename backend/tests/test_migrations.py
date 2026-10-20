import pytest
from alembic import command
from sqlalchemy import DateTime, inspect, text

pytestmark = pytest.mark.integration


def test_upgrade_downgrade_upgrade_and_metadata_match(migrated_engine, migration_runner):
    def tables():
        return set(inspect(migrated_engine).get_table_names(schema="public"))

    # The session fixture already applied upgrade head to the clean test database.
    assert tables() == {"users", "alembic_version"}
    with migrated_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM public.alembic_version")) == (
            "0001_create_users"
        )

    migration_runner(command.downgrade, "base")
    assert tables() == {"alembic_version"}
    with migrated_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM public.alembic_version")) == 0

    migration_runner(command.upgrade, "head")
    assert tables() == {"users", "alembic_version"}
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
    assert len(indexes) == 1  # The UNIQUE constraint already creates this index.
    assert indexes[0]["name"] == "uq_users_email"
    assert indexes[0]["unique"] is True
    assert indexes[0]["column_names"] == ["email"]
    migration_runner(command.check)
