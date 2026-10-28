"""Rule-based fraud-awareness checks. Deterministic and explainable; no AI involved.

Rules (each returns the set of flagged request_ids):
* duplicate_transaction      - same client and exact same amount within 10 minutes of an earlier request
* unusual_amount             - amount is a statistical outlier on the log scale (Tukey fence, k=3)
* repeated_failed_attempts   - 3 or more failed transactions by one client within 30 minutes
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def duplicate_transactions(df: pd.DataFrame, window_minutes: int = 10) -> set[str]:
    d = df.dropna(subset=["txn_amount"]).sort_values("created_at").copy()
    d["prev"] = d.groupby(["client_id", "txn_amount"])["created_at"].shift()
    hit = (d["created_at"] - d["prev"]) <= pd.Timedelta(minutes=window_minutes)
    return set(d.loc[hit, "request_id"])


def unusual_amounts(df: pd.DataFrame, k: float = 3.0) -> set[str]:
    d = df[df["txn_amount"] > 0].dropna(subset=["txn_amount"])
    logs = np.log(d["txn_amount"])
    q1, q3 = logs.quantile(0.25), logs.quantile(0.75)
    fence = q3 + k * (q3 - q1)
    return set(d.loc[logs > fence, "request_id"])


def repeated_failed_attempts(df: pd.DataFrame, n: int = 3, window_minutes: int = 30) -> set[str]:
    flagged: set[str] = set()
    failed = df[df["txn_status"] == "failed"].sort_values("created_at")
    window = pd.Timedelta(minutes=window_minutes)
    for _, g in failed.groupby("client_id"):
        ts, ids = g["created_at"].tolist(), g["request_id"].tolist()
        for i in range(len(ts)):
            j = i
            while j + 1 < len(ts) and ts[j + 1] - ts[i] <= window:
                j += 1
            if j - i + 1 >= n:
                flagged.update(ids[i : j + 1])
    return flagged


def run_all(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (request, rule) hit."""
    rules = {
        "duplicate_transaction": duplicate_transactions(df),
        "unusual_amount": unusual_amounts(df),
        "repeated_failed_attempts": repeated_failed_attempts(df),
    }
    rows = [{"request_id": rid, "rule": rule} for rule, ids in rules.items() for rid in sorted(ids)]
    return pd.DataFrame(rows, columns=["request_id", "rule"])
