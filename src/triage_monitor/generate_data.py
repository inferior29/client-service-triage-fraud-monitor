"""Deterministic generator for synthetic client service requests.

Everything here is fake: names, emails, phone numbers, account and card numbers.
Two files are written:

* requests.csv - what the pipeline sees (no labels)
* labels.csv   - ground truth used only for evaluation
"""
from __future__ import annotations

import argparse
import random
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .config import AS_OF, SLA_HOURS
from .policy import priority_policy

FIRST = ["Aarav", "Diya", "Rohan", "Ananya", "Vikram", "Meera", "Karthik", "Priya", "Sanjay",
         "Lakshmi", "Arjun", "Kavya", "Rahul", "Neha", "Suresh", "Pooja", "Imran", "Fatima"]
LAST = ["Reddy", "Sharma", "Iyer", "Nair", "Patel", "Gupta", "Rao", "Menon", "Khan", "Das",
        "Verma", "Chowdary", "Singh", "Joshi", "Naidu", "Pillai"]
CHANNELS = ["email", "chat", "phone", "portal"]

# category -> (weight, keyword templates, paraphrased templates)
TEMPLATES = {
    "payment_status": (20,
        ["Hi, this is {name}. Can you confirm the status of my payment of INR {amount}? Account {acct}. Reach me on {phone}.",
         "Payment status needed for transaction {ref} of INR {amount}. Regards, {name} ({email})"],
        ["I sent money yesterday and the other side says nothing arrived. Not sure where it is. {name}, {phone}",
         "Where is the amount of INR {amount} I transferred? My account is {acct}."]),
    "failed_transaction": (22,
        ["My transaction of INR {amount} failed but the money was debited from account {acct}. Please fix. {name} {phone}",
         "Transaction failed again for INR {amount}. Contact {email}."],
        ["I keep getting an error at the last step and nothing goes through. Account {acct}. - {name}",
         "The app says try later every time I pay INR {amount}. Call {phone}."]),
    "dispute_chargeback": (10,
        ["I want to raise a dispute for INR {amount} charged by a merchant I do not recognise. Card {card}. {name}, {email}",
         "Chargeback request for INR {amount}, transaction {ref}. Regards, {name}"],
        ["I was billed for something I returned weeks ago and nobody is refunding me. INR {amount}. {name} {phone}",
         "A shop took INR {amount} for a service never delivered, I want it reversed. {email}"]),
    "account_access": (14,
        ["My account {acct} is locked and I cannot login. Please reset password. {name} {phone}",
         "Unable to login, password reset link not coming to {email}."],
        ["I can not get into my profile since the weekend, it just keeps spinning. {name}, {phone}",
         "The code to verify me never arrives so I am stuck outside my account {acct}."]),
    "statement_request": (12,
        ["Please send my account statement for the last 6 months for account {acct}. {name}, {email}",
         "Need a statement copy for tax filing. Regards, {name}"],
        ["I need a record of all my activity for a loan application, whatever format you have. {name} {email}",
         "Could you share a document showing everything that went in and out of {acct} lately?"]),
    "fee_query": (10,
        ["Why was a fee of INR {amount} charged on account {acct}? Please explain the charges. {name}",
         "Query about service charges of INR {amount} on my statement. {phone}"],
        ["My balance is lower than I expected and I think something extra got deducted, INR {amount}. {name} {email}",
         "Is it normal that INR {amount} disappears every month? Account {acct}."]),
    "profile_update": (8,
        ["Please update my mobile number to {phone} and email to {email}. Account {acct}. {name}",
         "Change my registered address. Regards, {name} ({phone})"],
        ["I moved flats and my contact details are all out of date, who do I tell? {name} {email}",
         "My old number is no longer working so please use {phone} from now on."]),
    "suspected_fraud": (4,
        ["URGENT: unauthorised transaction of INR {amount} on my account {acct}, I did not make this. Block my card {card}. {name} {phone}",
         "I think my account is compromised, there are fraud transactions of INR {amount}. {email}"],
        ["Someone called pretending to be from the bank and now money is gone, INR {amount}. Please help. {name} {phone}",
         "There are payments on my account that I have never seen before, INR {amount}, I am scared. {acct}"]),
}
TXN_CATEGORIES = {"payment_status", "failed_transaction", "dispute_chargeback", "suspected_fraud"}
AMOUNT_MEDIAN = {"payment_status": 3000, "failed_transaction": 2500, "dispute_chargeback": 9000,
                 "suspected_fraud": 12000, "fee_query": 180}


def _make_clients(rng: random.Random, n_clients: int) -> list[dict]:
    clients = []
    for i in range(n_clients):
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        handle = name.lower().replace(" ", ".")
        clients.append({
            "client_id": f"C{i:04d}",
            "client_name": name,
            "email": f"{handle}{rng.randint(1, 999)}@example.com",
            "phone": f"+91 {rng.choice('6789')}{rng.randint(0, 9999):04d}{rng.randint(0, 99999):05d}",
            "account": f"{rng.randint(10**11, 10**12 - 1)}",
            "card": " ".join(f"{rng.randint(0, 9999):04d}" for _ in range(4)),
        })
    return clients


def generate(n: int = 5000, seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = random.Random(seed)
    nprng = np.random.default_rng(seed)
    clients = _make_clients(rng, 800)
    cats = list(TEMPLATES)
    weights = [TEMPLATES[c][0] for c in cats]
    start = AS_OF - timedelta(days=45)
    span_minutes = int((AS_OF - start).total_seconds() // 60)

    rows, labels = [], []
    for i in range(n):
        cat = rng.choices(cats, weights)[0]
        cl = rng.choice(clients)
        created = start + timedelta(minutes=rng.randint(0, span_minutes))
        median = AMOUNT_MEDIAN.get(cat)
        amount = round(float(nprng.lognormal(np.log(median), 0.9)), 2) if median else None
        style = rng.choices([1, 2], [0.7, 0.3])[0]  # 1 = keyword-rich, 2 = paraphrased
        template = rng.choice(TEMPLATES[cat][style])
        text = template.format(
            name=cl["client_name"], email=cl["email"], phone=cl["phone"], acct=cl["account"],
            card=cl["card"], ref=f"TXN{rng.randint(10**8, 10**9 - 1)}",
            amount=f"{amount:,.2f}" if amount is not None else "0",
        )
        is_txn = cat in TXN_CATEGORIES
        status = None
        if is_txn:
            status = "failed" if cat == "failed_transaction" else rng.choice(["success", "success", "pending"])
        priority = priority_policy(cat, amount if is_txn else None)
        if rng.random() < 0.05:  # label noise: an agent judged it one level differently
            k = int(priority[1]) + rng.choice([-1, 1])
            priority = f"P{min(4, max(1, k))}"
        rows.append({
            "request_id": f"R{i:05d}", "created_at": created, "channel": rng.choice(CHANNELS),
            "client_id": cl["client_id"], "client_name": cl["client_name"], "message": text,
            "txn_amount": amount if is_txn else np.nan, "txn_status": status,
            # PII fields the masker is tested against (the pipeline never forwards them):
            "_email": cl["email"], "_phone": cl["phone"], "_account": cl["account"], "_card": cl["card"],
        })
        labels.append({"request_id": f"R{i:05d}", "true_category": cat, "true_priority": priority,
                       "fraud_seed": "none"})

    df, lb = pd.DataFrame(rows), pd.DataFrame(labels)

    # ---- seed fraud patterns on transaction rows --------------------------------------
    txn_idx = df.index[df["txn_amount"].notna()].tolist()
    rng.shuffle(txn_idx)
    pool = iter(txn_idx)

    def take(k: int):
        """Next k unused transaction rows, or None when the sample is too small to seed more."""
        got = [next(pool, None) for _ in range(k)]
        return got if None not in got else None

    n_dup, n_unusual, n_burst = (max(1, round(n * f)) for f in (0.012, 0.008, 0.005))  # 60 / 40 / 25 at n=5000

    for _ in range(n_dup):  # duplicate transactions: same client + amount within minutes
        pair = take(2)
        if pair is None:
            break
        a, b = pair
        df.loc[b, ["client_id", "client_name", "_email", "_phone", "_account", "_card"]] = \
            df.loc[a, ["client_id", "client_name", "_email", "_phone", "_account", "_card"]].values
        df.loc[b, "txn_amount"] = df.loc[a, "txn_amount"]
        df.loc[b, "created_at"] = df.loc[a, "created_at"] + timedelta(minutes=rng.randint(1, 8))
        df.loc[[a, b], "txn_status"] = "success"
        lb.loc[b, "fraud_seed"] = "duplicate_transaction"

    for _ in range(n_unusual):  # unusual amounts
        one = take(1)
        if one is None:
            break
        (a,) = one
        df.loc[a, "txn_amount"] = round(rng.uniform(300_000, 900_000), 2)
        lb.loc[a, "fraud_seed"] = "unusual_amount"

    for _ in range(n_burst):  # repeated failed attempts: 3-5 failures by one client in 20 minutes
        group = take(rng.randint(3, 5))
        if group is None:
            break
        base = df.loc[group[0]]
        t0 = base["created_at"]
        for g in group:
            df.loc[g, ["client_id", "client_name", "_email", "_phone", "_account", "_card"]] = \
                base[["client_id", "client_name", "_email", "_phone", "_account", "_card"]].values
            df.loc[g, "created_at"] = t0 + timedelta(minutes=rng.randint(0, 20))
            df.loc[g, "txn_status"] = "failed"
            lb.loc[g, "fraud_seed"] = "repeated_failed_attempts"

    # Seeding re-assigned some rows to a different client, so rewrite those messages to embed
    # the new client's details (otherwise the text would carry another client's PII).
    for idx in df.index[lb["fraud_seed"] != "none"]:
        cat = lb.loc[idx, "true_category"]
        template = rng.choice(TEMPLATES[cat][1])
        amt = df.loc[idx, "txn_amount"]
        df.loc[idx, "message"] = template.format(
            name=df.loc[idx, "client_name"], email=df.loc[idx, "_email"], phone=df.loc[idx, "_phone"],
            acct=df.loc[idx, "_account"], card=df.loc[idx, "_card"],
            ref=f"TXN{rng.randint(10**8, 10**9 - 1)}", amount=f"{amt:,.2f}")

    # ---- resolution times -------------------------------------------------------------
    resolved_at, status = [], []
    for idx, row in df.iterrows():
        sla = SLA_HOURS[lb.loc[idx, "true_priority"]]
        hours = float(nprng.lognormal(np.log(sla * 0.55), 0.8))
        done = row["created_at"] + timedelta(hours=hours)
        age_days = (AS_OF - row["created_at"]).total_seconds() / 86400
        p_open = 0.02 if age_days > 7 else 0.10 if age_days > 2 else 0.30  # old requests are rarely still open
        if rng.random() < p_open or done > AS_OF:
            resolved_at.append(pd.NaT)
            status.append("open")
        else:
            resolved_at.append(done)
            status.append("resolved")
    df["resolved_at"] = resolved_at
    df["status"] = status
    return df.sort_values("created_at").reset_index(drop=True), lb


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="data")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    df, lb = generate(args.n, args.seed)
    df.to_csv(out / "requests.csv", index=False)
    lb.to_csv(out / "labels.csv", index=False)
    print(f"wrote {len(df)} requests -> {out}/requests.csv and labels.csv")


if __name__ == "__main__":
    main()
