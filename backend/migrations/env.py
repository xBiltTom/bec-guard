from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection

from app.core.config import Settings
from app.core.database import create_database_engine
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def include_name(name, type_, parent_names):
    if type_ == "schema":
        return name in (None, "public")
    if type_ == "table":
        # Ignore unmanaged tables as well as n8n during autogeneration.
        return f"public.{name}" in target_metadata.tables
    return True


def run_with_connection(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema="public",
        include_schemas=True,
        include_name=include_name,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(
        url=Settings().database_url,
        target_metadata=target_metadata,
        version_table_schema="public",
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    # Tests supply a connection to an explicitly isolated test database.
    connection = config.attributes.get("connection")
    if connection is not None:
        run_with_connection(connection)
    else:
        engine = create_database_engine(Settings())
        try:
            with engine.connect() as connection:
                run_with_connection(connection)
        finally:
            engine.dispose()
