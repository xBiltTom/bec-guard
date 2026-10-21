from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.core.tokens import create_access_token
from app.models import AuditLog, BECAlert, Role, User
from app.services.alerts import ensure_alert_for_analysis

pytestmark = pytest.mark.integration


@pytest.fixture
def review_setup(db_session, account, alert_setup, auth_settings):
    _, assessment, headers = alert_setup
    alert = ensure_alert_for_analysis(db_session, assessment(85), actor=account)
    other = User(name="Other", email="other@example.com", password_hash="opaque", role=Role.ANALYST)
    db_session.add(other)
    db_session.commit()
    other_headers = {"Authorization": f"Bearer {create_access_token(other.id, auth_settings)}"}
    return alert, headers, other, other_headers


def endpoint(alert, action):
    return f"/api/alerts/{alert.id}/{action}"


@pytest.mark.parametrize("verdict", ["CONFIRMED_BEC", "FALSE_POSITIVE"])
def test_full_review_cycle(api_client, db_session, account, review_setup, verdict):
    alert, headers, other, other_headers = review_setup
    assert (
        api_client.post(
            endpoint(alert, "resolve"),
            headers=headers,
            json={"verdict": verdict, "resolution": "Valid"},
        ).status_code
        == 409
    )
    claim = api_client.post(endpoint(alert, "claim"), headers=headers)
    assert claim.status_code == 200 and claim.json()["assigned_to"] == str(account.id)
    assert api_client.post(endpoint(alert, "claim"), headers=headers).json() == claim.json()
    assert api_client.post(endpoint(alert, "claim"), headers=other_headers).status_code == 409
    assert api_client.post(endpoint(alert, "release"), headers=other_headers).status_code == 403
    payload = {"verdict": verdict, "resolution": "  Private human decision  "}
    assert (
        api_client.post(endpoint(alert, "resolve"), headers=other_headers, json=payload).status_code
        == 403
    )
    result = api_client.post(endpoint(alert, "resolve"), headers=headers, json=payload)
    assert result.status_code == 200
    row = result.json()
    assert row["status"] == "CLOSED" and row["verdict"] == verdict
    assert row["resolution"] == payload["resolution"].strip()
    assert row["closed_at"].endswith("Z")
    assert api_client.post(endpoint(alert, "resolve"), headers=headers, json=payload).json() == row
    assert (
        api_client.post(
            endpoint(alert, "resolve"), headers=headers, json={**payload, "resolution": "Changed"}
        ).status_code
        == 409
    )
    for action in ("claim", "release"):
        assert api_client.post(endpoint(alert, action), headers=headers).status_code == 409
    events = list(db_session.scalars(select(AuditLog).where(AuditLog.action.like("BEC_ALERT_%"))))
    assert len(events) == 3
    assert events[-1].details is None
    assert {e.action for e in events} == {
        "BEC_ALERT_CREATED",
        "BEC_ALERT_CLAIMED",
        "BEC_ALERT_CONFIRMED" if verdict == "CONFIRMED_BEC" else "BEC_ALERT_FALSE_POSITIVE",
    }


@pytest.mark.parametrize("role", [Role.ADMIN, Role.MANAGER, Role.ANALYST])
def test_release_and_supervision(api_client, db_session, review_setup, role):
    alert, headers, other, other_headers = review_setup
    assert api_client.post(endpoint(alert, "release"), headers=headers).status_code == 200
    api_client.post(endpoint(alert, "claim"), headers=headers)
    other.role = role
    db_session.commit()
    result = api_client.post(endpoint(alert, "release"), headers=other_headers)
    assert result.status_code == (403 if role == Role.ANALYST else 200)
    if role == Role.ANALYST:
        result = api_client.post(endpoint(alert, "release"), headers=headers)
    assert result.json()["status"] == "OPEN" and result.json()["assigned_to"] is None
    api_client.post(endpoint(alert, "claim"), headers=headers)
    if role != Role.ANALYST:
        assert (
            api_client.post(
                endpoint(alert, "resolve"),
                headers=other_headers,
                json={"verdict": "FALSE_POSITIVE", "resolution": "Supervisor decision"},
            ).status_code
            == 200
        )


@pytest.mark.parametrize("resolution", ["", "   ", "x" * 2001, None])
def test_resolution_validation(api_client, review_setup, resolution):
    alert, headers, _, _ = review_setup
    assert (
        api_client.post(
            endpoint(alert, "resolve"),
            headers=headers,
            json={"verdict": "FALSE_POSITIVE", "resolution": resolution},
        ).status_code
        == 400
    )


def test_auditor_and_automation_cannot_review(api_client, db_session, account, review_setup):
    alert, headers, _, _ = review_setup
    account.role = Role.AUDITOR
    db_session.commit()
    for action in ("claim", "release", "resolve"):
        assert (
            api_client.post(
                endpoint(alert, action),
                headers=headers,
                json={"verdict": "FALSE_POSITIVE", "resolution": "Reason"},
            ).status_code
            == 403
        )
        assert (
            api_client.post(
                endpoint(alert, action), headers={"X-BEC-Automation-Key": "x" * 48}
            ).status_code
            == 401
        )


def test_claim_concurrent(api_client, review_setup):
    alert, headers, _, other_headers = review_setup
    with ThreadPoolExecutor(2) as pool:
        futures = [
            pool.submit(api_client.post, endpoint(alert, "claim"), headers=h)
            for h in (headers, other_headers)
        ]
        assert sorted(f.result().status_code for f in futures) == [200, 409]


@pytest.mark.parametrize(
    "changes",
    [
        "status='UNDER_REVIEW'",
        "status='CLOSED'",
        "resolution='Unexpected'",
        "verdict='FALSE_POSITIVE'",
    ],
)
def test_hitl_constraints(db_session, review_setup, changes):
    alert, _, _, _ = review_setup
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(f"UPDATE public.bec_alerts SET {changes} WHERE id=:id"), {"id": alert.id}
        )
        db_session.commit()
    db_session.rollback()


@pytest.mark.parametrize(
    "operation,action,verdict",
    [
        ("claim", "BEC_ALERT_CLAIMED", None),
        ("release", "BEC_ALERT_RELEASED", None),
        ("resolve", "BEC_ALERT_CONFIRMED", "CONFIRMED_BEC"),
        ("resolve", "BEC_ALERT_FALSE_POSITIVE", "FALSE_POSITIVE"),
    ],
)
def test_review_audit_rollback(
    api_client, db_session, migrated_engine, review_setup, operation, action, verdict
):
    alert, headers, _, _ = review_setup
    if operation != "claim":
        assert api_client.post(endpoint(alert, "claim"), headers=headers).status_code == 200
    with migrated_engine.begin() as c:
        c.execute(
            text(
                f"""CREATE FUNCTION public.reject_review_test() RETURNS trigger
                    LANGUAGE plpgsql AS $$ BEGIN
                    IF NEW.action = '{action}' THEN RAISE EXCEPTION 'test'; END IF;
                    RETURN NEW; END; $$"""
            )
        )
        c.execute(
            text(
                "CREATE TRIGGER reject_review_test BEFORE INSERT ON public.audit_log "
                "FOR EACH ROW EXECUTE FUNCTION public.reject_review_test()"
            )
        )
    try:
        assert (
            api_client.post(
                endpoint(alert, operation),
                headers=headers,
                json={"verdict": verdict, "resolution": "Private resolution"} if verdict else None,
            ).status_code
            == 503
        )
        db_session.expire_all()
        assert db_session.get(BECAlert, alert.id).status == (
            "OPEN" if operation == "claim" else "UNDER_REVIEW"
        )
        assert not list(db_session.scalars(select(AuditLog).where(AuditLog.action == action)))
    finally:
        db_session.rollback()
        with migrated_engine.begin() as c:
            c.execute(text("DROP TRIGGER reject_review_test ON public.audit_log"))
            c.execute(text("DROP FUNCTION public.reject_review_test()"))


def test_filters_dashboard_and_audit(api_client, review_setup, account):
    alert, headers, _, _ = review_setup
    for query in ("status=CLOSED", "risk_level=LOW", "bec_type=OTHER", f"assigned_to={uuid4()}"):
        assert api_client.get(f"/api/alerts?{query}", headers=headers).json() == []
    assert (
        len(
            api_client.get(
                f"/api/alerts?status=OPEN&risk_level=CRITICAL&analysis_id={alert.analysis_id}",
                headers=headers,
            ).json()
        )
        == 1
    )
    data = api_client.get("/api/dashboard/summary", headers=headers).json()
    assert data["emails_total"] == data["analyses_completed"] == data["alerts"]["open"] == 1
    assert data["risk_distribution"]["CRITICAL"] == 1
    assert (
        len(data["alerts_last_7_days"]) == 7
        and sum(d["count"] for d in data["alerts_last_7_days"]) == 1
    )


@pytest.mark.parametrize("role", list(Role))
def test_audit_read_roles(api_client, db_session, account, review_setup, role):
    _, headers, _, _ = review_setup
    account.role = role
    db_session.commit()
    result = api_client.get(
        "/api/audit?limit=1&action=BEC_ALERT_CREATED&resource_type=bec_alert", headers=headers
    )
    if role not in {Role.ADMIN, Role.AUDITOR}:
        assert result.status_code == 403
    else:
        assert result.status_code == 200 and len(result.json()) == 1
        assert result.json()[0]["actor_name"] == account.name
        assert (
            api_client.get("/api/audit?offset=1&action=BEC_ALERT_CREATED", headers=headers).json()
            == []
        )
        assert api_client.get("/api/audit?limit=101", headers=headers).status_code == 400


@pytest.mark.parametrize("field", ["assigned_to", "verdict", "resolution", "closed_at"])
def test_closed_requires_all_decision_fields(api_client, db_session, review_setup, field):
    alert, headers, _, _ = review_setup
    api_client.post(endpoint(alert, "claim"), headers=headers)
    assert (
        api_client.post(
            endpoint(alert, "resolve"),
            headers=headers,
            json={"verdict": "FALSE_POSITIVE", "resolution": "Verified locally"},
        ).status_code
        == 200
    )
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(f"UPDATE public.bec_alerts SET {field}=NULL WHERE id=:id"), {"id": alert.id}
        )
        db_session.commit()
    db_session.rollback()


def test_dashboard_reflects_human_decision(api_client, review_setup):
    alert, headers, _, _ = review_setup
    api_client.post(endpoint(alert, "claim"), headers=headers)
    assigned = api_client.get("/api/alerts?status=UNDER_REVIEW", headers=headers).json()
    assert assigned[0]["assigned_to_name"]
    api_client.post(
        endpoint(alert, "resolve"),
        headers=headers,
        json={"verdict": "CONFIRMED_BEC", "resolution": "Verified"},
    )
    data = api_client.get("/api/dashboard/summary", headers=headers).json()
    assert data["alerts"] == {"open": 0, "under_review": 0, "closed": 1}
    assert data["verdicts"] == {"confirmed_bec": 1, "false_positive": 0}
    assert sum(data["risk_distribution"].values()) == data["analyses_completed"]
