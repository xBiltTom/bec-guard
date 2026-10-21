import json
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[2] / "n8n/workflows/bec-analysis-webhook.json"


def test_workflow_is_native_importable_and_inactive():
    workflow = json.loads(WORKFLOW.read_text())
    assert workflow["active"] is False and workflow["pinData"] == {}
    nodes = {node["name"]: node for node in workflow["nodes"]}
    types = {node["type"] for node in nodes.values()}
    assert types == {
        f"n8n-nodes-base.{kind}"
        for kind in ["webhook", "httpRequest", "if", "switch", "set", "respondToWebhook"]
    }
    assert nodes["Webhook"]["parameters"]["path"] == "bec-guard/analyze"
    assert nodes["Webhook"]["parameters"]["authentication"] == "headerAuth"
    assert nodes["Respond"]["parameters"]["respondWith"] == "json"
    assert "/api/automation/emails'" in nodes["Ingest email"]["parameters"]["url"]
    assert "/analyze'" in nodes["Analyze email"]["parameters"]["url"]
    for name in ["Ingest email", "Analyze email"]:
        node = nodes[name]
        assert node["retryOnFail"] is False
        assert node["onError"] == "continueRegularOutput"
        response = node["parameters"]["options"]["response"]["response"]
        assert response["neverError"] is True and response["fullResponse"] is True
        assert "backend_url" in node["parameters"]["url"]
    for name, connection in workflow["connections"].items():
        assert name in nodes
        assert all(edge["node"] in nodes for output in connection["main"] for edge in output)


def test_routing_is_fail_closed_and_response_excludes_email_content():
    workflow = json.loads(WORKFLOW.read_text())
    nodes = {node["name"]: node for node in workflow["nodes"]}
    rules = nodes["Route result"]["parameters"]["rules"]["values"]
    assert [rule["outputKey"] for rule in rules] == ["ERROR", "ALERT", "NO_ALERT"]
    expressions = [r["conditions"]["conditions"][0]["leftValue"] for r in rules]
    assert "status === 'ERROR'" in expressions[0]
    assert "'HIGH', 'CRITICAL'" in expressions[1] and "alert_id" in expressions[1]
    assert "'LOW', 'MEDIUM'" in expressions[2] and "alert_id === null" in expressions[2]
    assert nodes["Route result"]["parameters"]["options"]["fallbackOutput"] == "extra"
    outputs = workflow["connections"]["Route result"]["main"]
    assert [out[0]["node"] for out in outputs] == ["ERROR", "ALERT", "NO_ALERT", "ERROR"]
    for name in ["ALERT", "NO_ALERT", "ERROR", "Ingest ERROR"]:
        response = nodes[name]["parameters"]["jsonOutput"]
        assert "body_text" not in response and "sender_email" not in response
        assert "subject" not in response and "credentials" not in response
        assert workflow["connections"][name]["main"][0][0]["node"] == "Respond"


def test_workflow_has_no_secrets_or_saved_execution_data():
    raw = WORKFLOW.read_text()
    workflow = json.loads(raw)
    assert "$env" not in raw  # Installed v2 blocks it; do not weaken global controls.
    assert "AUTOMATION_API_KEY" not in raw
    assert "Authorization" not in raw and "Bearer " not in raw
    assert "localhost" not in raw
    for node in workflow["nodes"]:
        for credential in node.get("credentials", {}).values():
            assert set(credential) == {"id", "name"}
    assert workflow["settings"] == {
        "executionOrder": "v1",
        "saveDataErrorExecution": "none",
        "saveDataSuccessExecution": "none",
        "saveManualExecutions": False,
        "saveExecutionProgress": False,
    }
