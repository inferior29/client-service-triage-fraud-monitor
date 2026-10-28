"""The service center's priority policy, written down once.

The keyword baseline applies it to its predicted category; the synthetic labels are generated
from it (plus a little noise) so the evaluation has something consistent to compare against.
"""
from __future__ import annotations


def priority_policy(category: str, amount: float | None) -> str:
    amount = amount or 0
    if category == "suspected_fraud":
        return "P1"
    if category == "dispute_chargeback" and amount >= 50_000:
        return "P1"
    if category in ("failed_transaction", "dispute_chargeback") and amount >= 20_000:
        return "P2"
    if category == "account_access":
        return "P2"
    if category in ("payment_status", "failed_transaction", "dispute_chargeback"):
        return "P3"
    return "P4"  # statement, fee and profile requests
