"""Shared constants. Everything that defines the triage taxonomy lives here."""
from __future__ import annotations

from datetime import datetime

# Fixed "now" so the synthetic data and every report are reproducible.
AS_OF = datetime(2026, 10, 27, 12, 0)

CATEGORIES = [
    "payment_status",
    "failed_transaction",
    "dispute_chargeback",
    "account_access",
    "statement_request",
    "fee_query",
    "profile_update",
    "suspected_fraud",
]
PRIORITIES = ["P1", "P2", "P3", "P4"]  # P1 = most urgent

# Hours allowed to resolve a request, by priority.
SLA_HOURS = {"P1": 4, "P2": 8, "P3": 24, "P4": 72}

# Work queue each category is routed to.
QUEUE_BY_CATEGORY = {
    "payment_status": "payments",
    "failed_transaction": "payments",
    "dispute_chargeback": "disputes",
    "account_access": "access",
    "statement_request": "servicing",
    "fee_query": "servicing",
    "profile_update": "servicing",
    "suspected_fraud": "fraud_desk",
}
FRAUD_QUEUE = "fraud_desk"

DEFAULT_NEXT_ACTION = {
    "payment_status": "Look up the transaction and reply with its current status.",
    "failed_transaction": "Check debit/credit entries and reverse or retry the failed transaction.",
    "dispute_chargeback": "Open a dispute case and request supporting documents from the client.",
    "account_access": "Verify identity through the approved process, then reset access.",
    "statement_request": "Generate the statement and send it to the registered email.",
    "fee_query": "Explain the fee from the tariff schedule; refund if it was charged in error.",
    "profile_update": "Verify identity, then update the contact details on file.",
    "suspected_fraud": "Block the card/account, escalate to the fraud desk, contact the client by phone.",
}
