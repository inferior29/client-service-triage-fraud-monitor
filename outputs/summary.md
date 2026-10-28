# Run summary

Backend: **rules**  |  Requests: **5000**  |  As-of: 2026-10-27 12:00

All data is synthetic. Scores compare the pipeline with labels the generator seeded; they show that
the pipeline is wired correctly, not how it would perform on real client traffic.

## Triage accuracy vs seeded labels
- Category accuracy: **74.7%**
- Priority accuracy: **81.4%**
- Escalation, triage only: precision 98.3%, recall 40.6% (172 flagged / 416 seeded)
- Escalation, after fraud rules: precision 99.1%, recall 82.9% (348 flagged / 416 seeded)

## Fraud-awareness rules vs seeded patterns
- Overall: precision 100.0%, recall 94.6% (193 flagged / 204 seeded)
- duplicate_transaction: precision 100.0%, recall 100.0% (60 flagged / 60 seeded)
- unusual_amount: precision 100.0%, recall 72.5% (29 flagged / 40 seeded)
- repeated_failed_attempts: precision 100.0%, recall 100.0% (104 flagged / 104 seeded)

## SLA breach by queue
| queue | total_requests | open_requests | breached_requests | open_and_overdue | breach_rate_pct | avg_hours_to_resolve |
|---|---|---|---|---|---|---|
| payments | 2744 | 157 | 878 | 112 | 32.0 | 22.1 |
| access | 444 | 21 | 120 | 19 | 27.0 | 6.0 |
| fraud_desk | 334 | 10 | 90 | 8 | 26.9 | 11.7 |
| servicing | 1048 | 92 | 233 | 37 | 22.2 | 51.2 |
| disputes | 430 | 17 | 88 | 11 | 20.5 | 14.9 |

## Open requests by age
| queue | 0-1 day | 1-3 days | 3-7 days | over 7 days | open_total |
|---|---|---|---|---|---|
| payments | 45 | 37 | 32 | 43 | 157 |
| servicing | 24 | 31 | 17 | 20 | 92 |
| access | 4 | 3 | 2 | 12 | 21 |
| disputes | 6 | 2 | 0 | 9 | 17 |
| fraud_desk | 2 | 2 | 1 | 5 | 10 |
