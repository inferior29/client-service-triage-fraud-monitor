"""PII masking. Runs BEFORE any text is sent to an AI model.

Layers:
1. Exact masking of the client's own CRM fields (name, email, phone, account, card) wherever
   they appear in the text.
2. Pattern masking for anything else that looks like an email, card, phone or long number.

Known limitation: free-text names that are NOT in the CRM record (for example a third party)
are not caught by regexes. A production version would add a named-entity recogniser and a
human spot-check. See README.
"""
from __future__ import annotations

import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
CARD = re.compile(r"(?<!\d)(?:\d{4}[ -]){3}\d{4}(?!\d)")
PHONE = re.compile(r"(?<!\d)(?:\+?91[ -]?)?[6-9]\d{4}[ -]?\d{5}(?!\d)")
LONG_NUMBER = re.compile(r"(?<!\d)\d{9,19}(?!\d)")


def _digits_only(value: str) -> str:
    return re.sub(r"\D", "", value)


def mask_text(text: str, *, name: str = "", email: str = "", phone: str = "",
              account: str = "", card: str = "") -> str:
    """Return `text` with personal data replaced by placeholders."""
    out = str(text)
    # Layer 1: exact CRM values (longest / most specific first).
    for value, token in ((email, "[EMAIL]"), (card, "[CARD]"), (phone, "[PHONE]"), (account, "[ACCOUNT]")):
        if value:
            out = out.replace(value, token)
    if name:
        out = re.sub(re.escape(name), "[NAME]", out, flags=re.IGNORECASE)
        for part in name.split():  # first/last name used on their own
            if len(part) > 2:
                out = re.sub(rf"\b{re.escape(part)}\b", "[NAME]", out, flags=re.IGNORECASE)
    # Layer 2: patterns.
    out = EMAIL.sub("[EMAIL]", out)
    out = CARD.sub("[CARD]", out)
    out = PHONE.sub("[PHONE]", out)
    out = LONG_NUMBER.sub("[ACCOUNT]", out)
    return out


def leaks(masked: str, *, name: str = "", email: str = "", phone: str = "",
          account: str = "", card: str = "") -> list[str]:
    """Names of the PII fields still present in `masked` (used in tests and as a runtime guard)."""
    found = []
    low = masked.lower()
    if email and email.lower() in low:
        found.append("email")
    if name and any(len(p) > 2 and p.lower() in low for p in name.split()):
        found.append("name")
    for label, value in (("phone", phone), ("account", account), ("card", card)):
        if value and _digits_only(value) and _digits_only(value) in _digits_only(masked):
            found.append(label)
    return found
