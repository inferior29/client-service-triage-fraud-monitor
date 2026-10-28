"""Triage backends: a keyword baseline and a Claude backend with structured JSON output.

Both return the same dict: category, priority, next_action, escalate.
The Claude backend only ever receives MASKED text (see pii.py).
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .config import CATEGORIES, DEFAULT_NEXT_ACTION, PRIORITIES
from .policy import priority_policy

# A deliberately generic lexicon, written without reference to the synthetic message templates,
# so the baseline is a fair "what a simple keyword filter would do" comparison.
KEYWORDS = {
    "suspected_fraud": ["fraud", "unauthorised", "unauthorized", "compromised", "scam", "did not make"],
    "dispute_chargeback": ["dispute", "chargeback", "refund", "merchant"],
    "account_access": ["locked", "login", "password", "reset"],
    "failed_transaction": ["failed", "declined", "debited"],
    "payment_status": ["status", "pending", "payment of"],
    "statement_request": ["statement"],
    "fee_query": ["fee", "charges", "charged"],
    "profile_update": ["update my", "change my", "registered"],
}


class RuleBackend:
    """Transparent keyword baseline. Used as the comparison point for the Claude backend."""

    name = "rules"

    def triage(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = payload["message"].lower()
        scores = {c: sum(k in text for k in kws) for c, kws in KEYWORDS.items()}
        best = max(CATEGORIES, key=lambda c: (scores[c], -CATEGORIES.index(c)))
        category = best if scores[best] > 0 else "payment_status"
        amount = payload.get("txn_amount")
        priority = priority_policy(category, amount if amount == amount else None)  # NaN-safe
        return {
            "category": category,
            "priority": priority,
            "next_action": DEFAULT_NEXT_ACTION[category],
            "escalate": priority == "P1" or category == "suspected_fraud",
        }


SYSTEM_PROMPT = (
    "You triage client service requests for a service center. The message text has had personal "
    "data replaced by placeholders such as [NAME] and [ACCOUNT]; never ask for or guess them. "
    "Pick exactly one category, a priority (P1 most urgent: suspected fraud or large disputed "
    "amounts; P2 failed or blocked access; P3 routine transaction queries; P4 informational), "
    "a one-sentence next action for the agent, and whether the case must be escalated. "
    "Always answer by calling the record_triage tool."
)

TRIAGE_TOOL = {
    "name": "record_triage",
    "description": "Record the triage decision for one client request.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": CATEGORIES},
            "priority": {"type": "string", "enum": PRIORITIES},
            "next_action": {"type": "string", "maxLength": 240},
            "escalate": {"type": "boolean"},
        },
        "required": ["category", "priority", "next_action", "escalate"],
    },
}

FALLBACK = {"category": "needs_review", "priority": "P3",
            "next_action": "Model output invalid or unavailable - route to a human agent.", "escalate": False}


def validate(result: Any) -> dict[str, Any] | None:
    """Accept a model answer only if it matches the schema exactly."""
    if not isinstance(result, dict):
        return None
    if result.get("category") not in CATEGORIES or result.get("priority") not in PRIORITIES:
        return None
    if not isinstance(result.get("next_action"), str) or not isinstance(result.get("escalate"), bool):
        return None
    return {k: result[k] for k in ("category", "priority", "next_action", "escalate")}


class ClaudeBackend:
    """Calls the Claude API with a forced tool call so the answer is structured JSON.

    Needs ANTHROPIC_API_KEY in the environment (never in code). Model is configurable with
    TRIAGE_MODEL. Any API error or schema violation falls back to a human-review result
    instead of guessing.
    """

    name = "claude"

    def __init__(self, client: Any = None, model: str | None = None):
        if client is None:
            import anthropic  # imported lazily so the rules backend needs no SDK

            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise RuntimeError("Set ANTHROPIC_API_KEY to use the Claude backend.")
            client = anthropic.Anthropic()
        self.client = client
        self.model = model or os.environ.get("TRIAGE_MODEL", "claude-haiku-5-5")

    def triage(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                system=SYSTEM_PROMPT,
                tools=[TRIAGE_TOOL],
                tool_choice={"type": "tool", "name": "record_triage"},
                messages=[{"role": "user", "content": json.dumps(payload, default=str)}],
            )
        except Exception:  # network/API failure: never crash the batch
            return dict(FALLBACK)
        for block in response.content:
            if getattr(block, "type", "") == "tool_use" and block.name == "record_triage":
                return validate(block.input) or dict(FALLBACK)
        return dict(FALLBACK)


def triage_all(backend: Any, payloads: list[dict[str, Any]], workers: int = 1) -> list[dict[str, Any]]:
    if workers <= 1:
        return [backend.triage(p) for p in payloads]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(backend.triage, payloads))
