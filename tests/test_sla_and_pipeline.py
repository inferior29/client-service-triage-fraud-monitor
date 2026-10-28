import pandas as pd

from triage_monitor.config import AS_OF
from triage_monitor.generate_data import generate
from triage_monitor.run import assemble, build_payloads, evaluate
from triage_monitor.sla_report import sla_reports
from triage_monitor.triage import RuleBackend, triage_all
from triage_monitor import fraud_rules


def test_sla_breach_and_ageing_counts_are_exact():
    # AS_OF = 2026-10-27 12:00. P1 SLA 4h, P3 SLA 24h.
    df = pd.DataFrame([
        # resolved in 3h (within P1 SLA) / 5h (breach)
        dict(request_id="1", queue="payments", priority="P1", status="resolved", created_at="2026-10-20 09:00", resolved_at="2026-10-20 12:00"),
        dict(request_id="2", queue="payments", priority="P1", status="resolved", created_at="2026-10-20 09:00", resolved_at="2026-10-20 14:00"),
        # open for 6h at AS_OF on P3 (within SLA) / open for 30h (overdue, 1-3 day bucket)
        dict(request_id="3", queue="payments", priority="P3", status="open", created_at="2026-10-27 06:00", resolved_at=None),
        dict(request_id="4", queue="access", priority="P3", status="open", created_at="2026-10-26 06:00", resolved_at=None),
    ])
    breach, ageing = sla_reports(df, as_of=AS_OF)
    pay = breach.set_index("queue").loc["payments"]
    assert (pay.total_requests, pay.open_requests, pay.breached_requests, pay.open_and_overdue) == (3, 1, 1, 0)
    assert pay.breach_rate_pct == 33.3
    acc = breach.set_index("queue").loc["access"]
    assert (acc.breached_requests, acc.open_and_overdue) == (1, 1)
    age = ageing.set_index("queue")
    assert age.loc["payments", "0-1 day"] == 1 and age.loc["access", "1-3 days"] == 1


def test_fraud_flagged_cases_are_routed_to_the_fraud_desk():
    req, labels = generate(n=800, seed=11)
    results = triage_all(RuleBackend(), build_payloads(req))
    flags = fraud_rules.run_all(req)
    out = assemble(req, results, flags)
    flagged = out[out["fraud_flagged"]]
    assert len(flagged) > 0
    assert (flagged["queue"] == "fraud_desk").all() and flagged["escalate_final"].all()
    ev = evaluate(out, labels)
    assert ev["escalation_after_fraud_rules"]["recall"] > ev["escalation_triage_only"]["recall"]


def test_generator_is_deterministic_and_labels_are_separate():
    a, la = generate(n=300, seed=9)
    b, lb = generate(n=300, seed=9)
    assert a.equals(b) and la.equals(lb)
    assert not {"true_category", "true_priority", "fraud_seed"} & set(a.columns)
