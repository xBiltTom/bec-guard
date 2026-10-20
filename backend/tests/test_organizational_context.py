import json
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.core.tokens import create_access_token
from app.models import AuditLog, ExecutiveContact, Role, User, Vendor
from app.services.organizational_context import (
    create_context,
    find_executive_by_email,
    find_vendor_by_domain,
    update_context,
)

pytestmark = pytest.mark.integration


@pytest.fixture(params=["executive", "vendor"])
def context(request):
    if request.param == "executive":
        return {
            "kind": "executive",
            "path": "/api/executives",
            "model": ExecutiveContact,
            "identity": "email",
            "canonical": "ceo@example.com",
            "body": {
                "name": "  Known Executive  ",
                "position": "  CEO  ",
                "department": "  Management  ",
                "email": "  CEO@Example.COM  ",
            },
            "lookup": find_executive_by_email,
        }
    return {
        "kind": "vendor",
        "path": "/api/vendors",
        "model": Vendor,
        "identity": "domain",
        "canonical": "example.com",
        "body": {
            "name": "  Known Vendor  ",
            "domain": " Example.COM. ",
            "contact_email": " Contact@Example.COM ",
            "bank_account_reference": "  opaque-bank-reference  ",
        },
        "lookup": find_vendor_by_domain,
    }


@pytest.fixture
def headers(account, db_session, auth_settings):
    account.role = Role.ADMIN
    db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(account.id, auth_settings)}"}


def test_crud_lookup_and_audit(api_client, db_session, account, headers, context):
    path = context["path"]
    response = api_client.post(path, json=context["body"], headers=headers)
    assert response.status_code == 201
    created = response.json()
    resource_id = UUID(created["id"])
    assert created[context["identity"]] == context["canonical"]
    assert created["name"] == context["body"]["name"].strip()
    assert created["is_active"] is True
    assert "password_hash" not in created
    if context["kind"] == "executive":
        assert created["position"] == "CEO"
        assert created["department"] == "Management"
    else:
        assert created["contact_email"] == "contact@example.com"
        assert created["bank_account_reference"] == "opaque-bank-reference"
    resource = db_session.get(context["model"], resource_id)
    assert resource.created_at.utcoffset() == timedelta(0)
    assert resource.updated_at.utcoffset() == timedelta(0)
    original_created = resource.created_at
    assert context["lookup"](db_session, context["body"][context["identity"]]).id == resource_id
    assert api_client.get(f"{path}/{resource_id}", headers=headers).json() == created
    assert api_client.get(path, headers=headers).json() == [created]

    for changes in [{"name": "  Renamed  "}, {"is_active": False}]:
        response = api_client.patch(f"{path}/{resource_id}", json=changes, headers=headers)
        assert response.status_code == 200
    assert api_client.get(path, headers=headers).json() == []
    assert len(api_client.get(path, params={"include_inactive": True}, headers=headers).json()) == 1
    assert api_client.get(f"{path}/{resource_id}", headers=headers).json()["is_active"] is False
    db_session.expire_all()
    assert context["lookup"](db_session, context["canonical"]) is None
    assert (
        context["lookup"](db_session, context["canonical"], include_inactive=True).id == resource_id
    )
    assert resource.created_at == original_created
    assert resource.updated_at > original_created
    assert (
        api_client.patch(
            f"{path}/{resource_id}", json={"is_active": True}, headers=headers
        ).status_code
        == 200
    )
    assert (
        api_client.patch(
            f"{path}/{resource_id}", json={"name": "Renamed"}, headers=headers
        ).status_code
        == 200
    )
    events = db_session.scalars(select(AuditLog).order_by(AuditLog.created_at)).all()
    prefix = context["kind"].upper()
    assert [event.action for event in events] == [
        f"{prefix}_CREATED",
        f"{prefix}_UPDATED",
        f"{prefix}_DEACTIVATED",
        f"{prefix}_REACTIVATED",
    ]
    for event in events:
        assert event.actor_user_id == account.id
        assert event.actor_role == Role.ADMIN
        assert event.resource_id == resource_id
        assert event.resource_type == context["kind"]
        assert event.created_at.utcoffset() == timedelta(0)
        assert event.ip_address is None  # TestClient peer isn't an IP.
        assert event.details is None or set(event.details) == {"changed_fields"}
        stored = json.dumps(event.details)
        for sensitive in [
            "opaque-bank-reference",
            "ceo@example.com",
            "contact@example.com",
            "Renamed",
            account.password_hash,
            headers["Authorization"],
        ]:
            assert sensitive not in stored
    assert events[1].details == {"changed_fields": "name"}
    assert api_client.delete(f"{path}/{resource_id}", headers=headers).status_code == 405


def test_identity_conflicts_create_and_patch(api_client, db_session, headers, context):
    path = context["path"]
    first = api_client.post(path, json=context["body"], headers=headers)
    assert first.status_code == 201
    assert api_client.post(path, json=context["body"], headers=headers).status_code == 409
    second_body = {
        **context["body"],
        context["identity"]: "other@example.com"
        if context["kind"] == "executive"
        else "other.example.com",
    }
    second = api_client.post(path, json=second_body, headers=headers).json()
    response = api_client.patch(
        f"{path}/{second['id']}",
        json={context["identity"]: context["canonical"].upper()},
        headers=headers,
    )
    assert response.status_code == 409
    assert "postgres" not in response.text.lower()
    assert (
        api_client.get(f"{path}/{second['id']}", headers=headers).json()[context["identity"]]
        == second_body[context["identity"]]
    )
    assert db_session.scalar(select(func.count()).select_from(AuditLog)) == 2


def test_database_itself_enforces_case_insensitive_identity(db_session, context):
    model = context["model"]
    values = {
        key: value.strip() if isinstance(value, str) else value
        for key, value in context["body"].items()
    }
    resource = model(**values)
    db_session.add(resource)
    db_session.commit()
    table = model.__tablename__
    # SQL bypasses Python normalization; identifiers are fixed fixture constants.
    columns = "id, name, position, email" if context["kind"] == "executive" else "id, name, domain"
    placeholders = (
        ":id, 'Duplicate', 'CEO', :identity"
        if context["kind"] == "executive"
        else ":id, 'Duplicate', :identity"
    )
    with pytest.raises(IntegrityError) as error:
        db_session.execute(
            text(f"INSERT INTO public.{table} ({columns}) VALUES ({placeholders})"),
            {"id": uuid4(), "identity": context["canonical"].upper()},
        )
    assert error.value.orig.sqlstate == "23505"
    db_session.rollback()


@pytest.mark.parametrize("role", list(Role))
def test_context_rbac(api_client, account, db_session, headers, context, role):
    path = context["path"]
    resource_id = api_client.post(path, json=context["body"], headers=headers).json()["id"]
    account.role = role
    db_session.commit()
    assert api_client.get(path, headers=headers).status_code == 200
    assert api_client.get(f"{path}/{resource_id}", headers=headers).status_code == 200
    allowed = role in {Role.ADMIN, Role.MANAGER}
    body = {
        **context["body"],
        context["identity"]: "next@example.com"
        if context["kind"] == "executive"
        else "next.example.com",
    }
    assert api_client.post(path, json=body, headers=headers).status_code == (
        201 if allowed else 403
    )
    assert api_client.patch(
        f"{path}/{resource_id}", json={"is_active": False}, headers=headers
    ).status_code == (200 if allowed else 403)
    if allowed:
        event = db_session.scalars(
            select(AuditLog).where(AuditLog.action.endswith("DEACTIVATED"))
        ).one()
        assert event.actor_role == role
    # Same token, role changed in DB: no stale role claim is accepted.
    account.role = Role.AUDITOR if allowed else Role.MANAGER
    db_session.commit()
    assert api_client.patch(
        f"{path}/{resource_id}", json={"name": "Changed role"}, headers=headers
    ).status_code == (403 if allowed else 200)
    account.is_active = False
    db_session.commit()
    assert api_client.get(path, headers=headers).status_code == 401


@pytest.mark.parametrize("method", ["get", "post", "patch"])
def test_context_requires_authentication(api_client, context, method):
    path = context["path"] + (f"/{uuid4()}" if method == "patch" else "")
    kwargs = {} if method == "get" else {"json": context["body"]}
    assert getattr(api_client, method)(path, **kwargs).status_code == 401


def test_pagination_and_missing_resources(api_client, headers, context):
    path = context["path"]
    for identity in [
        context["canonical"],
        "next@example.com" if context["kind"] == "executive" else "next.example.com",
    ]:
        assert (
            api_client.post(
                path, json={**context["body"], context["identity"]: identity}, headers=headers
            ).status_code
            == 201
        )
    first = api_client.get(path, params={"limit": 1}, headers=headers).json()
    second = api_client.get(path, params={"limit": 1, "offset": 1}, headers=headers).json()
    assert len(first) == len(second) == 1
    assert first[0]["id"] != second[0]["id"]
    assert api_client.get(path, params={"offset": 2}, headers=headers).json() == []
    for query in [{"limit": 101}, {"limit": 0}, {"offset": -1}]:
        assert api_client.get(path, params=query, headers=headers).status_code == 400
    assert api_client.get(f"{path}/{uuid4()}", headers=headers).status_code == 404
    assert (
        api_client.patch(f"{path}/{uuid4()}", json={"name": "Unknown"}, headers=headers).status_code
        == 404
    )
    assert api_client.get(f"{path}/invalid-uuid", headers=headers).status_code == 400


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": None},
        {"is_active": None},
        {"name": "  "},
        {"unknown": "opaque-bank-reference"},
        {"name": "x" * 201},
    ],
)
def test_invalid_patches_are_sanitized(api_client, headers, context, body):
    response = api_client.patch(f"{context['path']}/{uuid4()}", json=body, headers=headers)
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request"}


def test_nullable_fields_and_private_bank_updates(api_client, db_session, headers):
    vendor = api_client.post(
        "/api/vendors", json={"name": "Supplier", "domain": "supplier.example.com"}, headers=headers
    ).json()
    response = api_client.patch(
        f"/api/vendors/{vendor['id']}",
        json={
            "contact_email": " SALES@example.com ",
            "bank_account_reference": "  new-private-bank  ",
        },
        headers=headers,
    )
    assert response.json()["bank_account_reference"] == "new-private-bank"
    assert response.json()["contact_email"] == "sales@example.com"
    details = db_session.scalars(
        select(AuditLog.details).where(AuditLog.action == "VENDOR_UPDATED")
    ).one()
    assert details == {"changed_fields": "bank_account_reference,contact_email"}
    assert "new-private-bank" not in json.dumps(details)
    cleared = api_client.patch(
        f"/api/vendors/{vendor['id']}",
        json={"contact_email": None, "bank_account_reference": " "},
        headers=headers,
    )
    assert cleared.json()["contact_email"] is None
    assert cleared.json()["bank_account_reference"] is None
    invalid = api_client.patch(
        f"/api/vendors/{vendor['id']}",
        json={"bank_account_reference": "private-bank" * 30},
        headers=headers,
    )
    assert invalid.status_code == 400
    assert "private-bank" not in invalid.text


@pytest.mark.parametrize("operation", ["create", "update"])
def test_resource_rolls_back_when_real_audit_insert_fails(db_session, account, context, operation):
    resource = context["model"](**context["body"])
    if operation == "update":
        db_session.add(resource)
        db_session.commit()
        resource_id = resource.id
        old_name = resource.name
    # A non-existent actor causes a real PostgreSQL FK violation during audit INSERT.
    missing_actor = User(id=uuid4(), role=Role.ADMIN)
    with pytest.raises(IntegrityError) as error:
        if operation == "create":
            create_context(db_session, resource, actor=missing_actor)
        else:
            update_context(db_session, resource, {"name": "Must roll back"}, actor=missing_actor)
    assert error.value.orig.sqlstate == "23503"  # Unknown errors aren't converted to 409.
    if operation == "create":
        assert db_session.scalar(select(func.count()).select_from(context["model"])) == 0
    else:
        assert db_session.get(context["model"], resource_id).name == old_name
    assert db_session.scalar(select(func.count()).select_from(AuditLog)) == 0


@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/executives", {"name": "CEO", "position": "CEO", "email": "invalid"}),
        ("/api/executives", {"name": "CEO", "position": " ", "email": "ceo@example.com"}),
        ("/api/vendors", {"name": "Supplier", "domain": "https://example.com"}),
        ("/api/vendors", {"name": "Supplier", "domain": "example.com", "contact_email": "invalid"}),
    ],
)
def test_invalid_create_returns_sanitized_400(api_client, headers, path, body):
    response = api_client.post(path, json=body, headers=headers)
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request"}


def test_optional_department_can_be_cleared(api_client, headers):
    created = api_client.post(
        "/api/executives",
        headers=headers,
        json={
            "name": "Executive",
            "position": "CEO",
            "department": "Management",
            "email": "executive@example.com",
        },
    ).json()
    response = api_client.patch(
        f"/api/executives/{created['id']}", headers=headers, json={"department": None}
    )
    assert response.status_code == 200
    assert response.json()["department"] is None
