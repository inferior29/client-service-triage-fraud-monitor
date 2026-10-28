"""SLA ageing and breach reports, written in SQL (SQLite) and run from Python."""
from __future__ import annotations

import sqlite3

import pandas as pd

from .config import AS_OF, SLA_HOURS

# Elapsed time = (resolved_at, or "now" for open requests) - created_at.
BASE_CTE = """
WITH base AS (
    SELECT request_id, queue, priority, status,
           CASE priority WHEN 'P1' THEN :p1 WHEN 'P2' THEN :p2 WHEN 'P3' THEN :p3 ELSE :p4 END AS sla_hours,
           (julianday(COALESCE(resolved_at, :as_of)) - julianday(created_at)) * 24.0 AS elapsed_hours
    FROM requests
)
"""

BREACH_BY_QUEUE_SQL = BASE_CTE + """
SELECT queue,
       COUNT(*)                                              AS total_requests,
       SUM(status = 'open')                                  AS open_requests,
       SUM(elapsed_hours > sla_hours)                        AS breached_requests,
       SUM(status = 'open' AND elapsed_hours > sla_hours)    AS open_and_overdue,
       ROUND(100.0 * SUM(elapsed_hours > sla_hours) / COUNT(*), 1) AS breach_rate_pct,
       ROUND(AVG(CASE WHEN status = 'resolved' THEN elapsed_hours END), 1) AS avg_hours_to_resolve
FROM base
GROUP BY queue
ORDER BY breach_rate_pct DESC, queue
"""

OPEN_AGEING_SQL = BASE_CTE + """
SELECT queue,
       SUM(elapsed_hours <= 24)                         AS "0-1 day",
       SUM(elapsed_hours > 24  AND elapsed_hours <= 72) AS "1-3 days",
       SUM(elapsed_hours > 72  AND elapsed_hours <= 168) AS "3-7 days",
       SUM(elapsed_hours > 168)                         AS "over 7 days",
       COUNT(*)                                         AS open_total
FROM base
WHERE status = 'open'
GROUP BY queue
ORDER BY open_total DESC, queue
"""


def _connect(df: pd.DataFrame) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    d = df[["request_id", "queue", "priority", "status", "created_at", "resolved_at"]].copy()
    for col in ("created_at", "resolved_at"):
        d[col] = pd.to_datetime(d[col]).dt.strftime("%Y-%m-%d %H:%M:%S")
    d.to_sql("requests", con, index=False)
    return con


def _params(as_of=AS_OF) -> dict:
    return {"as_of": pd.Timestamp(as_of).strftime("%Y-%m-%d %H:%M:%S"),
            "p1": SLA_HOURS["P1"], "p2": SLA_HOURS["P2"], "p3": SLA_HOURS["P3"], "p4": SLA_HOURS["P4"]}


def sla_reports(df: pd.DataFrame, as_of=AS_OF) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`df` needs: request_id, queue, priority, status, created_at, resolved_at."""
    con = _connect(df)
    try:
        breach = pd.read_sql_query(BREACH_BY_QUEUE_SQL, con, params=_params(as_of))
        ageing = pd.read_sql_query(OPEN_AGEING_SQL, con, params=_params(as_of))
    finally:
        con.close()
    return breach, ageing
