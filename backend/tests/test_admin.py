import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.core.passwords import verify_password
from app.models import Role, User
from app.services.admin import AdminBootstrapError, create_initial_admin

pytestmark = pytest.mark.integration


def test_bootstrap_admin(db_session):
    admin = create_initial_admin(
        db_session,
        name=" Initial Admin ",
        email="  Admin@Example.COM  ",
        password="a long test password",
    )
    assert admin.role is Role.ADMIN
    assert admin.name == "Initial Admin"
    assert admin.email == "admin@example.com"
    assert verify_password("a long test password", admin.password_hash)
    with pytest.raises(AdminBootstrapError):
        create_initial_admin(
            db_session, name="Second", email="admin@example.com", password="a long test password"
        )


def test_database_case_insensitive_uniqueness(db_session):
    admin = create_initial_admin(
        db_session, name="Admin", email="admin@example.com", password="a long test password"
    )
    with pytest.raises(IntegrityError) as error:
        db_session.execute(
            text(
                "INSERT INTO public.users (id, name, email, password_hash, role) "
                "SELECT gen_random_uuid(), name, 'ADMIN@EXAMPLE.COM', password_hash, role "
                "FROM public.users WHERE id = :id"
            ),
            {"id": admin.id},
        )
    assert error.value.orig.diag.constraint_name == "uq_users_email_lower"
    db_session.rollback()


def test_bootstrap_rejects_email_owned_by_non_admin(db_session, account):
    with pytest.raises(AdminBootstrapError):
        create_initial_admin(
            db_session,
            name="Admin",
            email="  ANALYST@example.com ",
            password="a long test password",
        )
    assert (
        db_session.scalar(select(func.count()).select_from(User).where(User.role == Role.ADMIN))
        == 0
    )
