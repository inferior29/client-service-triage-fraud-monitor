import pandas as pd
import pytest

from triage_monitor.generate_data import generate
from triage_monitor.pii import leaks, mask_text
from triage_monitor.run import PII_COLUMNS, build_payloads

PII = dict(name="Aarav Reddy", email="aarav.reddy7@example.com", phone="+91 9876543210",
           account="123456789012", card="4111 1111 1111 1111")


def test_masks_every_field():
    text = ("Hi, this is Aarav Reddy. Mail aarav.reddy7@example.com or call +91 9876543210. "
            "Account 123456789012, card 4111 1111 1111 1111.")
    out = mask_text(text, **PII)
    assert out == "Hi, this is [NAME]. Mail [EMAIL] or call [PHONE]. Account [ACCOUNT], card [CARD]."
    assert leaks(out, **PII) == []


def test_pattern_layer_catches_pii_not_in_crm_record():
    out = mask_text("Also reach my brother at other.person@mail.com or 9123456780, ref 987654321098")
    assert "other.person@mail.com" not in out and "9123456780" not in out and "987654321098" not in out


def test_amounts_and_words_survive():
    out = mask_text("Payment of INR 2,500.00 failed", **PII)
    assert out == "Payment of INR 2,500.00 failed"


def test_leaks_detects_unmasked_value():
    assert "email" in leaks("contact aarav.reddy7@example.com", **PII)


def test_no_pii_in_any_payload_sent_to_a_model():
    """Strongest check: across 1,500 generated requests, no payload contains any of that row's PII."""
    req, _ = generate(n=1500, seed=3)
    payloads = build_payloads(req)
    for row, payload in zip(req.to_dict("records"), payloads):
        pii = {k: str(row[col]) for k, col in PII_COLUMNS.items()}
        assert leaks(payload["message"], **pii) == []
        blob = str(payload)
        assert row["client_id"] not in blob  # internal client ids are not forwarded either


def test_pipeline_refuses_to_continue_if_pii_survives(monkeypatch):
    req, _ = generate(n=20, seed=1)
    monkeypatch.setattr("triage_monitor.run.mask_text", lambda text, **kw: text)  # simulate a broken masker
    with pytest.raises(RuntimeError, match="survived masking"):
        build_payloads(req)
