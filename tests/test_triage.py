from types import SimpleNamespace

from triage_monitor.generate_data import generate
from triage_monitor.run import build_payloads
from triage_monitor.triage import FALLBACK, ClaudeBackend, RuleBackend, validate

GOOD = {"category": "failed_transaction", "priority": "P2", "next_action": "Reverse the debit.", "escalate": False}


class FakeClient:
    """Mimics anthropic.Anthropic().messages.create without any network."""

    def __init__(self, content=None, error=None):
        self.calls, self._content, self._error = [], content, error
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return SimpleNamespace(content=self._content)


def tool_block(data, name="record_triage"):
    return SimpleNamespace(type="tool_use", name=name, input=data)


PAYLOAD = {"message": "My payment failed [ACCOUNT]", "channel": "chat", "txn_amount": 100.0, "txn_status": "failed"}


def test_claude_backend_returns_valid_structured_result():
    client = FakeClient([tool_block(GOOD)])
    assert ClaudeBackend(client=client, model="m").triage(PAYLOAD) == GOOD


def test_request_forces_the_tool_call_with_an_enum_schema():
    client = FakeClient([tool_block(GOOD)])
    ClaudeBackend(client=client, model="m").triage(PAYLOAD)
    call = client.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": "record_triage"}
    schema = call["tools"][0]["input_schema"]
    assert "payment_status" in schema["properties"]["category"]["enum"]
    assert schema["properties"]["priority"]["enum"] == ["P1", "P2", "P3", "P4"]


def test_invalid_enum_falls_back_to_human_review():
    bad = dict(GOOD, category="made_up_category")
    assert ClaudeBackend(client=FakeClient([tool_block(bad)]), model="m").triage(PAYLOAD) == FALLBACK


def test_wrong_types_are_rejected():
    assert validate(dict(GOOD, escalate="yes")) is None
    assert validate(dict(GOOD, next_action=None)) is None
    assert validate("not a dict") is None


def test_api_error_falls_back_instead_of_crashing():
    assert ClaudeBackend(client=FakeClient(error=RuntimeError("503")), model="m").triage(PAYLOAD) == FALLBACK


def test_text_only_answer_falls_back():
    text_only = [SimpleNamespace(type="text", text="I think it is fraud")]
    assert ClaudeBackend(client=FakeClient(text_only), model="m").triage(PAYLOAD) == FALLBACK


def test_what_claude_receives_is_masked():
    req, _ = generate(n=60, seed=5)
    client = FakeClient([tool_block(GOOD)])
    backend = ClaudeBackend(client=client, model="m")
    for payload in build_payloads(req):
        backend.triage(payload)
    sent = " ".join(c["messages"][0]["content"] for c in client.calls)
    for row in req.to_dict("records"):
        for field in ("client_name", "_email", "_phone", "_account", "_card"):
            assert str(row[field]) not in sent


def test_rule_baseline_applies_priority_policy():
    r = RuleBackend().triage({"message": "Unauthorised transaction on my account", "txn_amount": 900.0})
    assert (r["category"], r["priority"], r["escalate"]) == ("suspected_fraud", "P1", True)
    vague = RuleBackend().triage({"message": "Something odd happened", "txn_amount": float("nan")})
    assert vague["category"] == "payment_status"  # documented default for no keyword hit
