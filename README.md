# AI-Assisted Client Service Triage & Fraud-Flag Monitor

A small, end-to-end service-center workflow built on **synthetic data**:

1. **Mask personal data** in every client message *before* any AI call (and abort if anything slips through).
2. **Triage** each request with Claude using structured JSON output: category, priority, next action, escalate yes/no.
   A transparent keyword baseline runs the same pipeline so the AI can be compared with something simple.
3. **Fraud-awareness rules** (duplicate transactions, unusual amounts, repeated failed attempts) route flagged cases to the fraud desk.
4. **SLA ageing and breach report** per queue, written in SQL.

```
requests.csv ──► PII masking ──► triage (Claude | keyword baseline) ──┐
      │                                                               ├─► queue + escalation ─► SLA SQL report ─► summary.md
      └──────────► fraud rules (duplicates / outliers / failed bursts) ┘
```

## Run it

```bash
pip install -r requirements.txt
export PYTHONPATH=src                              # or: pip install -e .
python -m triage_monitor.generate_data --out data  # 5,000 synthetic requests + separate labels.csv
python -m triage_monitor.run --backend rules       # baseline, no API key needed
pytest -q                                          # 21 tests

# Claude backend (needs your own key; the key is read from the environment, never from code)
export ANTHROPIC_API_KEY=...
python -m triage_monitor.run --backend claude --limit 300 --workers 8   # --limit controls cost
```

Outputs land in `outputs/`: `triage_results.csv`, `fraud_flags.csv`, `sla_breach_by_queue.csv`,
`open_requests_ageing.csv`, `summary.md`.

## Results (keyword baseline, synthetic data, seed 42)

| Measure | Result |
|---|---|
| Category accuracy | 74.7% |
| Priority accuracy | 81.4% |
| Escalation recall, triage only | 40.6% |
| Escalation recall, after fraud rules | 82.9% |
| Fraud rules overall | precision 100%, recall 94.6% (193 of 204 seeded cases) |
| Unusual-amount rule | recall 72.5%: it misses seeded outliers that sit inside the statistical fence |

**Claude backend: not yet measured.** It is unit-tested against a fake client (request shape, forced tool call, schema
validation, fallbacks) but has not been run against the live API in this repo's history. Run the command above with your own
key and paste the `summary.md` numbers here next to the baseline.

These scores compare the pipeline with labels the generator seeded. They show the wiring works. They are **not** a
claim about accuracy on real client traffic.

## Design notes

- **Labels are separate from inputs.** The generator writes `requests.csv` (what the pipeline sees) and `labels.csv` (ground truth for evaluation only).
- **PII masking is layered.** Exact CRM values (name, email, phone, account, card) are masked first, then regex patterns catch anything else. A runtime guard aborts the batch if any of the client's own details survive. A test checks 1,500 payloads.
- **Structured output.** The Claude call forces a `record_triage` tool call whose schema has enums for category and priority. Anything that fails validation, or any API error, becomes a `needs_review` result routed to a human. It never guesses.
- **Fraud rules are deterministic on purpose.** They are explainable and testable, and they do not depend on the model.
- **Baseline lexicon is generic.** It was written without reference to the message templates, so 74.7% is what a naive filter would get, not a number tuned to look good.

## Limitations (read before quoting any number)

- Everything is synthetic. Messages come from templates, so real language will be messier.
- Name masking relies on the CRM record plus patterns. A third party's name typed into free text would not be caught; production use needs a named-entity recogniser and human sampling.
- Label noise (5% of priorities shifted one level) is injected to mimic agent disagreement.
- The `claude-haiku-5-5` default model name is configurable with `TRIAGE_MODEL`.

## Layout

```
src/triage_monitor/  generate_data.py  pii.py  triage.py  fraud_rules.py  sla_report.py  run.py  policy.py  config.py
tests/               PII, fraud rules, Claude backend (fake client), SLA SQL, pipeline
data/ outputs/       generated inputs and the latest run's reports
```
