import sys
from getpass import getpass

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.core.database import create_database_engine, create_session_factory
from app.services.admin import create_initial_admin


def main() -> int:
    if not sys.stdin.isatty():
        print("Run this command in an interactive terminal; passwords are never CLI arguments.")
        return 1
    engine = None
    try:
        name = input("Name: ")
        email = input("Email: ")
        password = getpass("Password (12–128 characters): ")
        if password != getpass("Confirm password: "):
            print("Passwords do not match.")
            return 1
        engine = create_database_engine(Settings())
        with create_session_factory(engine)() as session:
            admin = create_initial_admin(session, name=name, email=email, password=password)
            print(f"Initial ADMIN created: {admin.id}")
        return 0
    except ValueError, EOFError, KeyboardInterrupt:
        print("Could not create ADMIN: invalid input, password policy, or identity conflict.")
        return 1
    except SQLAlchemyError:
        print("Database unavailable or migrations pending.")
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
