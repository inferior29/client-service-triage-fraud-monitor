"""End-to-end pipeline: mask -> triage -> fraud rules -> SLA reports -> evaluation.

    python -m triage_monitor.run --backend rules
    ANTHROPIC_API_KEY=... python -m triage_monitor.run --backend claude --limit 300 --workers 8
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from . import fraud_rules
from .config import AS_OF, FRAUD_QUEUE, QUEUE_BY_CATEGORY
from .pii import leaks, mask_text
from .sla_report import sla_reports
from .triage import ClaudeBackend, RuleBackend, triage_all

PII_COLUMNS = {"name": "client_name", "email": "_email", "phone": "_phone", "account": "_account", "card": "_card"}


def build_payloads(req: pd.DataFrame) -> list[dict]:
    """Mask every message and refuse to continue if any personal data survived."""
    payloads = []
    for r in req.to_dict("records"):
        pii = {k: str(r[col]) for k, col in PII_COLUMNS.items()}
        masked = mask_text(r["message"], **pii)
        still_there = leaks(masked, **pii)
        if still_there:
            raise RuntimeError(f"PII ({still_there}) survived masking for {r['request_id']}; aborting before any AI call")
        amount = r["txn_amount"]
        payloads.append({
            "message": masked,
            "channel": r["channel"],
            "txn_amount": None if pd.isna(amount) else float(amount),
            "txn_status": None if pd.isna(r["txn_status"]) else r["txn_status"],
        })
    return payloads


def assemble(req: pd.DataFrame, results: list[dict], flags: pd.DataFrame) -> pd.DataFrame:
    out = req[["request_id", "created_at", "resolved_at", "status", "channel", "client_id"]].copy()
    tri = pd.DataFrame(results, index=req.index)
    out = pd.concat([out, tri.rename(columns={"escalate": "escalate_triage"})], axis=1)
    rule_hits = flags.groupby("request_id")["rule"].apply(lambda s: ";".join(sorted(s))) if len(flags) else pd.Series(dtype=str)
    out["fraud_rules"] = out["request_id"].map(rule_hits).fillna("")
    out["fraud_flagged"] = out["fraud_rules"] != ""
    out["escalate_final"] = out["escalate_triage"] | out["fraud_flagged"]
    out["queue"] = out["category"].map(QUEUE_BY_CATEGORY).fillna("human_review")
    out.loc[out["fraud_flagged"], "queue"] = FRAUD_QUEUE  # flagged cases always go to escalation
    return out


def evaluate(out: pd.DataFrame, labels: pd.DataFrame) -> dict:
    m = out.merge(labels, on="request_id", how="left")
    true_escalate = (m["true_priority"] == "P1") | (m["fraud_seed"] != "none")

    def prf(pred: pd.Series, truth: pd.Series) -> dict:
        tp = int((pred & truth).sum())
        return {"precision": tp / max(int(pred.sum()), 1), "recall": tp / max(int(truth.sum()), 1),
                "flagged": int(pred.sum()), "actual": int(truth.sum())}

    per_rule = {}
    for rule in ("duplicate_transaction", "unusual_amount", "repeated_failed_attempts"):
        pred = m["fraud_rules"].str.contains(rule)
        per_rule[rule] = prf(pred, m["fraud_seed"] == rule)
    return {
        "n": len(m),
        "category_accuracy": float((m["category"] == m["true_category"]).mean()),
        "priority_accuracy": float((m["priority"] == m["true_priority"]).mean()),
        "escalation_triage_only": prf(m["escalate_triage"], true_escalate),
        "escalation_after_fraud_rules": prf(m["escalate_final"], true_escalate),
        "fraud_overall": prf(m["fraud_flagged"], m["fraud_seed"] != "none"),
        "fraud_by_rule": per_rule,
    }


def _md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    lines += ["| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def write_summary(path: Path, backend: str, ev: dict, breach: pd.DataFrame, ageing: pd.DataFrame) -> None:
    pct = lambda x: f"{100 * x:.1f}%"
    prf = lambda d: f"precision {pct(d['precision'])}, recall {pct(d['recall'])} ({d['flagged']} flagged / {d['actual']} seeded)"
    text = f"""# Run summary

Backend: **{backend}**  |  Requests: **{ev['n']}**  |  As-of: {AS_OF:%Y-%m-%d %H:%M}

All data is synthetic. Scores compare the pipeline with labels the generator seeded; they show that
the pipeline is wired correctly, not how it would perform on real client traffic.

## Triage accuracy vs seeded labels
- Category accuracy: **{pct(ev['category_accuracy'])}**
- Priority accuracy: **{pct(ev['priority_accuracy'])}**
- Escalation, triage only: {prf(ev['escalation_triage_only'])}
- Escalation, after fraud rules: {prf(ev['escalation_after_fraud_rules'])}

## Fraud-awareness rules vs seeded patterns
- Overall: {prf(ev['fraud_overall'])}
""" + "\n".join(f"- {k}: {prf(v)}" for k, v in ev["fraud_by_rule"].items()) + f"""

## SLA breach by queue
{_md_table(breach)}

## Open requests by age
{_md_table(ageing)}
"""
    path.write_text(text)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="outputs")
    ap.add_argument("--backend", choices=["rules", "claude"], default="rules")
    ap.add_argument("--limit", type=int, default=0, help="triage only a random sample of N requests (cost control)")
    ap.add_argument("--workers", type=int, default=1)
    args = ap.parse_args()

    data, out_dir = Path(args.data), Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    req = pd.read_csv(data / "requests.csv", parse_dates=["created_at", "resolved_at"])
    labels = pd.read_csv(data / "labels.csv")
    if args.limit:
        req = req.sample(args.limit, random_state=7).sort_values("created_at").reset_index(drop=True)

    backend = ClaudeBackend() if args.backend == "claude" else RuleBackend()
    results = triage_all(backend, build_payloads(req), workers=args.workers)
    flags = fraud_rules.run_all(req)
    out = assemble(req, results, flags)
    breach, ageing = sla_reports(out)

    out.to_csv(out_dir / "triage_results.csv", index=False)
    flags.to_csv(out_dir / "fraud_flags.csv", index=False)
    breach.to_csv(out_dir / "sla_breach_by_queue.csv", index=False)
    ageing.to_csv(out_dir / "open_requests_ageing.csv", index=False)
    ev = evaluate(out, labels)
    write_summary(out_dir / "summary.md", backend.name, ev, breach, ageing)
    print((out_dir / "summary.md").read_text())


if __name__ == "__main__":
    main()
