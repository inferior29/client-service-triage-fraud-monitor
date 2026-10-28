import pandas as pd

from triage_monitor import fraud_rules as fr


def frame(rows):
    df = pd.DataFrame(rows, columns=["request_id", "client_id", "created_at", "txn_amount", "txn_status"])
    df["created_at"] = pd.to_datetime(df["created_at"])
    return df


def test_duplicate_flags_only_the_later_request():
    df = frame([("R1", "C1", "2026-10-01 10:00", 500.0, "success"),
                ("R2", "C1", "2026-10-01 10:06", 500.0, "success"),      # same client+amount, 6 min later
                ("R3", "C1", "2026-10-01 11:00", 500.0, "success"),      # outside the 10-minute window
                ("R4", "C2", "2026-10-01 10:01", 500.0, "success")])     # different client
    assert fr.duplicate_transactions(df) == {"R2"}


def test_unusual_amount_uses_log_scale_fence():
    amounts = [1000 + 10 * i for i in range(40)] + [900_000]
    df = frame([(f"R{i}", f"C{i}", "2026-10-01 10:00", a, "success") for i, a in enumerate(amounts)])
    assert fr.unusual_amounts(df) == {"R40"}


def test_repeated_failed_attempts_needs_three_within_window():
    df = frame([("A1", "C1", "2026-10-01 10:00", 10.0, "failed"),
                ("A2", "C1", "2026-10-01 10:10", 10.0, "failed"),
                ("A3", "C1", "2026-10-01 10:25", 10.0, "failed"),        # 3 within 30 min -> flagged
                ("B1", "C2", "2026-10-01 10:00", 10.0, "failed"),
                ("B2", "C2", "2026-10-01 10:20", 10.0, "failed"),
                ("B3", "C2", "2026-10-01 11:30", 10.0, "failed"),        # third is too late -> not flagged
                ("D1", "C3", "2026-10-01 10:00", 10.0, "success"),
                ("D2", "C3", "2026-10-01 10:05", 10.0, "success"),
                ("D3", "C3", "2026-10-01 10:09", 10.0, "success")])
    assert fr.repeated_failed_attempts(df) == {"A1", "A2", "A3"}


def test_run_all_returns_one_row_per_rule_hit():
    df = frame([("R1", "C1", "2026-10-01 10:00", 500.0, "failed"),
                ("R2", "C1", "2026-10-01 10:03", 500.0, "failed"),
                ("R3", "C1", "2026-10-01 10:05", 520.0, "failed")])
    flags = fr.run_all(df)
    assert set(flags["rule"]) == {"duplicate_transaction", "repeated_failed_attempts"}
    assert set(flags.loc[flags["rule"] == "repeated_failed_attempts", "request_id"]) == {"R1", "R2", "R3"}
