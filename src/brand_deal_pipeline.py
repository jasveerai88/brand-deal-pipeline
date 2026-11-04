#!/usr/bin/env python3
"""brand-deal-pipeline — a local board of brand deals that tells a
creator what is due, what is delivered-but-unpaid, and which
invoices are quietly aging.

Pure Python standard library. Local only: no network, no uploads,
no accounts. Your deal list never leaves your machine.

A brand deal is not done when the brand says yes. It is done when
you are paid — and between "yes" and "paid" there are a dozen ways
for it to die quietly: a deliverable whose date slipped past, work
delivered weeks ago that was never invoiced, an invoice sitting in
someone's inbox while you assume it is "in the process". Agency
CRMs fix that for teams, at a monthly price, with a pipeline board
built for account managers. This tool is one JSON file and four
commands, built for one creator.

The board is a single JSON file (created by your first `add`):
  {"deals": [ {entry}, ... ]}

Entry fields:
  id          integer, assigned by `add` (never reused)
  brand       the brand the deal is with (required, non-empty)
  contact     who you deal with there (may be empty)
  deliverable what you owe them (required, non-empty)
  fee         the agreed fee in CAD (required, >= 0)
  status      "pitched" | "negotiating" | "agreed" | "delivered"
              | "invoiced" | "paid" | "dead" (default "pitched")
  due         deliverable due date, YYYY-MM-DD (or null)
  invoiced    invoice date, YYYY-MM-DD (or null; required once a
              deal is invoiced or paid)

Commands:
  add       --brand B --deliverable D --fee F [--contact C]
            [--status S] [--due D] [--invoiced D]
  list      every deal, plus the money totals
  move      ID STATUS — move a deal along the pipeline. The
            stages flow pitched -> negotiating -> agreed ->
            delivered -> invoiced -> paid, and any live deal can
            be marked dead. "paid" and "dead" are TERMINAL: a deal
            cannot be moved out of them. Moving to "invoiced"
            stamps the invoice date (today) if none is recorded.
  due       [--today D] — the work view:
              DELIVERABLES DUE   agreed deals whose deliverable is
                overdue or due within 7 days (day 7 counts, day 8
                does not)
              DELIVERED — NOT INVOICED   work is out, the invoice
                is not; the payment clock has not even started
              INVOICES OVERDUE   invoiced 30+ days, still unpaid
              INVOICES TO CHASE  invoiced 14–29 days, still unpaid
            Deliverables and invoices each get a polite, copy-ready
            line built ONLY from facts on the board — brand,
            contact, deliverable, fee and the real dates. No fake
            urgency, no invented payment terms.

Totals are shown everywhere: pipeline value by status, money
delivered-but-unpaid (delivered + invoiced), and money paid. An
agreed fee is not income; only "paid" is money in.

Fees are CAD. --cad-to-inr R also prints INR equivalents (rate R
per 1 CAD), following the CAD + INR display pattern of
payout-tracker.

Exit codes: 0 = ok / nothing due · 1 = `due` found at least one
action item (a finding, so a reminder script can act on it) ·
2 = ERROR — clean message, never a traceback; with --json the
error is {"error": ...}. A corrupt board is an error and is NEVER
overwritten or silently wiped.
"""
import argparse
import json
import math
import os
import re
import sys
from datetime import date
from pathlib import Path

__version__ = "0.1.0"
TOOL = "brand-deal-pipeline"

STATUSES = ("pitched", "negotiating", "agreed", "delivered",
            "invoiced", "paid", "dead")
TERMINAL = ("paid", "dead")
TRANSITIONS = {
    "pitched": ("negotiating", "agreed", "dead"),
    "negotiating": ("pitched", "agreed", "dead"),
    "agreed": ("delivered", "dead"),
    "delivered": ("invoiced", "dead"),
    "invoiced": ("paid", "dead"),
    "paid": (),
    "dead": (),
}
DUE_WINDOW_DAYS = 7        # deliverable due within this = due soon
CHASE_DAYS = 14            # unpaid invoice this old = chase it
OVERDUE_DAYS = 30          # unpaid invoice this old = overdue
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ToolError(Exception):
    """A clean, user-facing failure (printed as ERROR, exit 2)."""


# --------------------------------------------------------------------------
# dates
# --------------------------------------------------------------------------

def parse_date(value, label):
    """Strict YYYY-MM-DD -> date, or a clean ToolError naming `label`."""
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise ToolError(f"{label} must be a date as YYYY-MM-DD "
                        f"(got {value!r})")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ToolError(f"{label} is not a real calendar date: {value!r}")


def today_arg(value):
    """Resolve an optional --today flag to a date (default: today)."""
    if value is None:
        return date.today()
    return parse_date(value, "--today")


# --------------------------------------------------------------------------
# board loading + validation (a corrupt board is never wiped)
# --------------------------------------------------------------------------

def _fail_entry(no, msg):
    raise ToolError(f"entry {no}: {msg}")


def _check_fee(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value):
        raise ToolError(f"{label} must be a finite number (got {value!r})")
    if value < 0:
        raise ToolError(f"{label} must be >= 0 (got {value})")
    return float(value)


def _opt_date(raw, field, no):
    """An optional date field: null/missing -> None, else strict."""
    value = raw.get(field)
    if value is None:
        return None
    try:
        return parse_date(value, f"'{field}'").isoformat()
    except ToolError as exc:
        _fail_entry(no, str(exc))


def normalize_entry(raw, no):
    """Validate one raw board entry -> a clean entry dict."""
    if not isinstance(raw, dict):
        _fail_entry(no, f"expected an object of fields, got {raw!r}")
    entry_id = raw.get("id")
    if isinstance(entry_id, bool) or not isinstance(entry_id, int) \
            or entry_id < 1:
        _fail_entry(no, f"'id' must be a positive whole number "
                        f"(got {entry_id!r})")
    brand = raw.get("brand")
    if not isinstance(brand, str) or not brand.strip():
        _fail_entry(no, "'brand' is required and must be a non-empty "
                        "string")
    contact = raw.get("contact", "")
    if not isinstance(contact, str):
        _fail_entry(no, f"'contact' must be a string (got {contact!r})")
    deliverable = raw.get("deliverable")
    if not isinstance(deliverable, str) or not deliverable.strip():
        _fail_entry(no, "'deliverable' is required and must be a "
                        "non-empty string")
    if "fee" not in raw:
        _fail_entry(no, "missing required field 'fee'")
    try:
        fee = _check_fee(raw["fee"], "'fee'")
    except ToolError as exc:
        _fail_entry(no, str(exc))
    status = raw.get("status", "pitched")
    if status not in STATUSES:
        _fail_entry(no, f"'status' must be one of "
                        f"{'/'.join(STATUSES)} (got {status!r})")
    due = _opt_date(raw, "due", no)
    invoiced = _opt_date(raw, "invoiced", no)
    if status in ("invoiced", "paid") and invoiced is None:
        _fail_entry(no, f"status is '{status}' but there is no "
                        f"'invoiced' date — an invoiced deal needs "
                        f"the date its invoice went out")
    return {
        "id": entry_id,
        "brand": brand.strip(),
        "contact": contact.strip(),
        "deliverable": deliverable.strip(),
        "fee": fee,
        "status": status,
        "due": due,
        "invoiced": invoiced,
    }


def _reject_json_constant(name):
    raise ValueError(f"invalid constant {name}")


def load_board(path, must_exist=True):
    """Read + validate the board file -> list of clean entry dicts.

    Raises ToolError on anything wrong. The file is only ever READ
    here; a corrupt board is reported, never repaired in place.
    """
    if not path.is_file():
        if must_exist:
            raise ToolError(f"board not found: {path} — add a deal "
                            f"first (the board is created by `add`)")
        return []
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise ToolError(f"could not read board {path.name} "
                        f"({exc.__class__.__name__}) — the file was "
                        f"left untouched")
    try:
        data = json.loads(text, parse_constant=_reject_json_constant)
    except ValueError as exc:
        raise ToolError(f"board {path.name} is not valid JSON: {exc} "
                        f"— the file was left untouched")
    if isinstance(data, dict):
        if "deals" not in data:
            raise ToolError(f"board {path.name}: a JSON object must "
                            f"hold the entries under a \"deals\" key "
                            f"— the file was left untouched")
        data = data["deals"]
    if not isinstance(data, list):
        raise ToolError(f"board {path.name}: expected a JSON list of "
                        f"deals (or an object with \"deals\") — the "
                        f"file was left untouched")
    entries = [normalize_entry(raw, i + 1) for i, raw in enumerate(data)]
    seen = set()
    for e in entries:
        if e["id"] in seen:
            raise ToolError(f"board {path.name}: duplicate id "
                            f"{e['id']} — ids must be unique; the "
                            f"file was left untouched")
        seen.add(e["id"])
    return entries


def save_board(path, entries):
    """Write the board atomically (temp file in the same folder, then
    replace) so a crash mid-write can never leave a half board."""
    payload = {"deals": entries}
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        raise ToolError(f"could not write board {path} "
                        f"({exc.__class__.__name__}: {exc})")


# --------------------------------------------------------------------------
# the logic — due states, aging, messages, totals
# --------------------------------------------------------------------------

def _days(n):
    return f"{n} day" + ("" if n == 1 else "s")


def deliverable_state(entry, today):
    """For an AGREED deal with a due date: ("overdue", days_late) or
    ("due_soon", days_left) when it lands inside the window, else
    None. Boundaries are exact: due in exactly 7 days counts,
    8 days does not; due yesterday is 1 day overdue."""
    if entry["status"] != "agreed" or entry["due"] is None:
        return None
    delta = (date.fromisoformat(entry["due"]) - today).days
    if delta < 0:
        return ("overdue", -delta)
    if delta <= DUE_WINDOW_DAYS:
        return ("due_soon", delta)
    return None


def invoice_age_days(entry, today):
    """Days since the invoice went out, for an unpaid (invoiced)
    deal — else None."""
    if entry["status"] != "invoiced" or entry["invoiced"] is None:
        return None
    return (today - date.fromisoformat(entry["invoiced"])).days


def invoice_state(entry, today):
    """("overdue", age) at 30+ days, ("chase", age) at 14–29, else
    None. Boundaries are exact: day 14 chases, day 30 is overdue."""
    age = invoice_age_days(entry, today)
    if age is None:
        return None
    if age >= OVERDUE_DAYS:
        return ("overdue", age)
    if age >= CHASE_DAYS:
        return ("chase", age)
    return None


def _greeting(entry):
    return f"Hi {entry['contact']}" if entry["contact"] else "Hi there"


def deliverable_message(entry, today):
    """A polite line to the contact about the deliverable, built
    ONLY from facts on the board: brand, contact, deliverable, fee
    and the real due date. No fake urgency, nothing invented."""
    state, n = deliverable_state(entry, today)
    fee = _fmt_money(entry["fee"])
    if state == "overdue":
        return (f"{_greeting(entry)}, a quick update on the "
                f"{entry['deliverable']} for {entry['brand']} "
                f"({fee}): it was due on {entry['due']}, "
                f"{_days(n)} ago. It is still in progress on my "
                f"side — I'll confirm a revised delivery date as "
                f"soon as I have one, and I'm sorry for the slip.")
    if n == 0:
        return (f"{_greeting(entry)}, confirming the "
                f"{entry['deliverable']} for {entry['brand']} "
                f"({fee}) is due today, {entry['due']}. I'll send "
                f"it over as soon as it is ready.")
    return (f"{_greeting(entry)}, confirming the "
            f"{entry['deliverable']} for {entry['brand']} ({fee}) "
            f"is due on {entry['due']} — {_days(n)} from now. I'll "
            f"send it over as soon as it is ready.")


def invoice_message(entry, today):
    """A polite chase line about an unpaid invoice, built ONLY from
    facts on the board. It never invents payment terms (no
    "net-30", no late fees) — it states the invoice, the amount
    and how long it has actually been out."""
    state, age = invoice_state(entry, today)
    fee = _fmt_money(entry["fee"])
    if state == "overdue":
        return (f"{_greeting(entry)}, following up again on the "
                f"invoice for {entry['deliverable']} ({fee}) for "
                f"{entry['brand']}, sent on {entry['invoiced']} — "
                f"{_days(age)} ago now. If anything is missing from "
                f"my side to process it, I'm happy to send it over; "
                f"otherwise I'd appreciate an update on when it "
                f"will be paid.")
    return (f"{_greeting(entry)}, following up on the invoice for "
            f"{entry['deliverable']} ({fee}) for {entry['brand']}, "
            f"sent on {entry['invoiced']} — {_days(age)} ago. "
            f"Could you let me know whether it is in the payment "
            f"queue, or if you need anything else from me to "
            f"process it?")


def delivered_next_step(entry):
    """Delivered work with no invoice out is money standing still —
    the next step is yours, not the brand's."""
    fee = _fmt_money(entry["fee"])
    due_note = (f" (deliverable was due {entry['due']})"
                if entry["due"] else "")
    return (f"Send the invoice for this deal ({fee}){due_note} — "
            f"the work is delivered, and the payment clock only "
            f"starts once the invoice is out.")


def annotate(entry, today):
    """An entry plus its computed view fields for `today`."""
    out = dict(entry)
    out["days_until_due"] = (
        (date.fromisoformat(entry["due"]) - today).days
        if entry["due"] else None)
    out["invoice_age_days"] = invoice_age_days(entry, today)
    return out


def build_due(entries, today):
    """The work view for `today`: four action groups, plus the
    counts of things that are fine for now."""
    deliverables, delivered, chase, overdue = [], [], [], []
    current_invoices = 0
    future_deliverables = 0
    for e in entries:
        view = annotate(e, today)
        dstate = deliverable_state(e, today)
        if dstate:
            view["state"], view["days"] = dstate
            view["message"] = deliverable_message(e, today)
            deliverables.append(view)
        elif e["status"] == "agreed" and e["due"] is not None:
            future_deliverables += 1
        if e["status"] == "delivered":
            view2 = dict(view)
            view2["next_step"] = delivered_next_step(e)
            delivered.append(view2)
        istate = invoice_state(e, today)
        if istate:
            view3 = dict(view)
            view3["state"], view3["days"] = istate
            view3["message"] = invoice_message(e, today)
            (overdue if istate[0] == "overdue" else chase).append(view3)
        elif e["status"] == "invoiced":
            current_invoices += 1
    # deliverables: most overdue first, then soonest due first
    deliverables.sort(key=lambda e: (0, -e["days"], e["id"])
                      if e["state"] == "overdue"
                      else (1, e["days"], e["id"]))
    delivered.sort(key=lambda e: e["id"])
    chase.sort(key=lambda e: (-e["days"], e["id"]))
    overdue.sort(key=lambda e: (-e["days"], e["id"]))
    return {
        "deliverables": deliverables,
        "delivered_uninvoiced": delivered,
        "invoices_chase": chase,
        "invoices_overdue": overdue,
        "current_invoices": current_invoices,
        "future_deliverables": future_deliverables,
    }


def action_count(due_view):
    return (len(due_view["deliverables"])
            + len(due_view["delivered_uninvoiced"])
            + len(due_view["invoices_chase"])
            + len(due_view["invoices_overdue"]))


def compute_totals(entries):
    by_status = {s: {"count": 0, "amount": 0.0} for s in STATUSES}
    for e in entries:
        by_status[e["status"]]["count"] += 1
        by_status[e["status"]]["amount"] += e["fee"]
    delivered_unpaid = (by_status["delivered"]["amount"]
                        + by_status["invoiced"]["amount"])
    return {
        "by_status": by_status,
        "delivered_unpaid": delivered_unpaid,
        "paid": by_status["paid"]["amount"],
    }


def find_entry(entries, entry_id):
    for e in entries:
        if e["id"] == entry_id:
            return e
    raise ToolError(f"no deal with id {entry_id} on this board")


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def _fmt_money(value, cad_to_inr=None):
    text = f"${value:,.2f}"
    if cad_to_inr is not None:
        text += f" (₹{value * cad_to_inr:,.0f})"
    return text


def _with_inr(obj, fields, cad_to_inr):
    if cad_to_inr is None:
        return obj
    for f in fields:
        if obj.get(f) is not None:
            obj[f + "_inr"] = round(obj[f] * cad_to_inr, 2)
    return obj


def _entry_json(e, cad_to_inr, with_view=True):
    obj = {
        "id": e["id"],
        "brand": e["brand"],
        "contact": e["contact"],
        "deliverable": e["deliverable"],
        "fee": round(e["fee"], 2),
        "status": e["status"],
        "due": e["due"],
        "invoiced": e["invoiced"],
    }
    if with_view:
        for field in ("days_until_due", "invoice_age_days", "state",
                      "days", "message", "next_step"):
            if field in e:
                obj[field] = e[field]
    return _with_inr(obj, ("fee",), cad_to_inr)


def _totals_json(totals, cad_to_inr):
    by_status = {}
    for status in STATUSES:
        t = {"count": totals["by_status"][status]["count"],
             "amount": round(totals["by_status"][status]["amount"], 2)}
        by_status[status] = _with_inr(t, ("amount",), cad_to_inr)
    obj = {"by_status": by_status,
           "delivered_unpaid": round(totals["delivered_unpaid"], 2),
           "paid": round(totals["paid"], 2)}
    return _with_inr(obj, ("delivered_unpaid", "paid"), cad_to_inr)


def _totals_lines(totals, cad_to_inr):
    parts = []
    for s in STATUSES:
        t = totals["by_status"][s]
        parts.append(f"{s} {_fmt_money(t['amount'], cad_to_inr)} "
                     f"({t['count']})")
    return [
        "TOTALS by status: " + " · ".join(parts),
        f"Delivered but unpaid: "
        f"{_fmt_money(totals['delivered_unpaid'], cad_to_inr)}"
        f" · Paid: {_fmt_money(totals['paid'], cad_to_inr)}",
    ]


def _header(command, board_name, today, cad_to_inr):
    return [
        f"brand-deal-pipeline v{__version__} — {command} · board "
        f"{board_name} · today {today.isoformat()}",
        "Amounts in CAD."
        + (f" INR equivalents at {cad_to_inr:g} per CAD dollar."
           if cad_to_inr is not None else ""),
    ]


def _entry_line(e, cad_to_inr=None):
    line = f"#{e['id']} · {e['brand']}"
    if e["contact"]:
        line += f" ({e['contact']})"
    line += (f" — {e['deliverable']} — "
             f"{_fmt_money(e['fee'], cad_to_inr)} — {e['status']}")
    if e["due"]:
        line += f" — deliverable due {e['due']}"
    if e["invoiced"]:
        line += f" — invoiced {e['invoiced']}"
    return line


def render_due_text(due_view, totals, board_name, today, cad_to_inr):
    lines = _header("due", board_name, today, cad_to_inr)
    lines.append("")
    if action_count(due_view) == 0:
        lines.append(f"Nothing due — no deliverable due within "
                     f"{DUE_WINDOW_DAYS} days, no delivered work "
                     f"waiting on an invoice, and no invoice unpaid "
                     f"for {CHASE_DAYS}+ days.")
    group = due_view["deliverables"]
    if group:
        lines.append(f"DELIVERABLES DUE — agreed deals overdue or "
                     f"due within {DUE_WINDOW_DAYS} days "
                     f"({len(group)}):")
        for e in group:
            note = (f"{_days(e['days'])} overdue"
                    if e["state"] == "overdue"
                    else "due today" if e["days"] == 0
                    else f"due in {_days(e['days'])}")
            lines.append(_entry_line(e, cad_to_inr) + f" ({note})")
            lines.append(f"   → {e['message']}")
        lines.append("")
    group = due_view["delivered_uninvoiced"]
    if group:
        lines.append(f"DELIVERED — INVOICE NOT SENT YET "
                     f"({len(group)}):")
        for e in group:
            lines.append(_entry_line(e, cad_to_inr))
            lines.append(f"   → {e['next_step']}")
        lines.append("")
    group = due_view["invoices_overdue"]
    if group:
        lines.append(f"INVOICES OVERDUE — unpaid for {OVERDUE_DAYS}+ "
                     f"days ({len(group)}):")
        for e in group:
            lines.append(_entry_line(e, cad_to_inr)
                         + f" (invoice out {_days(e['days'])})")
            lines.append(f"   → {e['message']}")
        lines.append("")
    group = due_view["invoices_chase"]
    if group:
        lines.append(f"INVOICES TO CHASE — unpaid for {CHASE_DAYS}+ "
                     f"days ({len(group)}):")
        for e in group:
            lines.append(_entry_line(e, cad_to_inr)
                         + f" (invoice out {_days(e['days'])})")
            lines.append(f"   → {e['message']}")
        lines.append("")
    lines.extend(_totals_lines(totals, cad_to_inr))
    lines.append(f"Action items: {action_count(due_view)} · "
                 f"Invoices still current (< {CHASE_DAYS} days): "
                 f"{due_view['current_invoices']} · Deliverables "
                 f"further out (> {DUE_WINDOW_DAYS} days): "
                 f"{due_view['future_deliverables']}")
    return "\n".join(lines)


def due_as_json(due_view, totals, board_name, today, cad_to_inr):
    return {
        "tool": TOOL, "version": __version__, "command": "due",
        "board": board_name, "today": today.isoformat(),
        "cad_to_inr": cad_to_inr,
        "deliverables": [_entry_json(e, cad_to_inr)
                         for e in due_view["deliverables"]],
        "delivered_uninvoiced": [
            _entry_json(e, cad_to_inr)
            for e in due_view["delivered_uninvoiced"]],
        "invoices_chase": [_entry_json(e, cad_to_inr)
                           for e in due_view["invoices_chase"]],
        "invoices_overdue": [_entry_json(e, cad_to_inr)
                             for e in due_view["invoices_overdue"]],
        "current_invoices": due_view["current_invoices"],
        "future_deliverables": due_view["future_deliverables"],
        "action_items": action_count(due_view),
        "totals": _totals_json(totals, cad_to_inr),
    }


def render_list_text(annotated, totals, board_name, today, cad_to_inr):
    lines = _header("list", board_name, today, cad_to_inr)
    lines.append("")
    if not annotated:
        lines.append("No deals on this board yet — add one with "
                     "`add`.")
    for e in sorted(annotated, key=lambda x: x["id"]):
        lines.append(_entry_line(e, cad_to_inr))
    lines.append("")
    lines.extend(_totals_lines(totals, cad_to_inr))
    return "\n".join(lines)


def list_as_json(annotated, totals, board_name, today, cad_to_inr):
    return {
        "tool": TOOL, "version": __version__, "command": "list",
        "board": board_name, "today": today.isoformat(),
        "cad_to_inr": cad_to_inr,
        "deals": [_entry_json(e, cad_to_inr)
                  for e in sorted(annotated, key=lambda x: x["id"])],
        "totals": _totals_json(totals, cad_to_inr),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

class _JsonAwareParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors as JSON in --json mode
    ({"error": ...} on stdout, same exit code 2) — an agent driving
    this tool with --json never gets plain text or a traceback. The
    flag lives on the class so subparsers share it."""

    json_mode = False

    def error(self, message):
        if self.json_mode:
            print(json.dumps({"error": message}))
            self.exit(2)
        super().error(message)


def _cad_to_inr(a):
    rate = getattr(a, "cad_to_inr", None)
    if rate is None:
        return None
    if not math.isfinite(rate) or rate <= 0:
        raise ToolError(f"--cad-to-inr must be a positive finite "
                        f"number (got {rate!r})")
    return rate


def _board_arg(p):
    p.add_argument("--board", default="deals.json",
                   help="board file (default: deals.json in the "
                        "current folder)")


def _json_arg(p):
    p.add_argument("--json", action="store_true",
                   help="print one JSON object instead of text")


def _inr_arg(p):
    p.add_argument("--cad-to-inr", type=float, default=None,
                   help="also print INR equivalents at this rate per "
                        "1 CAD dollar")


def _today_arg(p):
    p.add_argument("--today", default=None,
                   help="pretend today is this date (YYYY-MM-DD) — "
                        "for reminder scripts and tests")


def cmd_add(a):
    cad_to_inr = _cad_to_inr(a)
    path = Path(a.board)
    entries = load_board(path, must_exist=False)
    today = today_arg(a.today)
    fee = _check_fee(a.fee, "--fee")
    brand = a.brand.strip()
    if not brand:
        raise ToolError("--brand must be a non-empty string")
    deliverable = a.deliverable.strip()
    if not deliverable:
        raise ToolError("--deliverable must be a non-empty string")
    due = (parse_date(a.due, "--due").isoformat() if a.due else None)
    invoiced = (parse_date(a.invoiced, "--invoiced").isoformat()
                if a.invoiced else None)
    if a.status in ("invoiced", "paid") and invoiced is None:
        invoiced = today.isoformat()
    entry = {
        "id": max((e["id"] for e in entries), default=0) + 1,
        "brand": brand,
        "contact": a.contact.strip(),
        "deliverable": deliverable,
        "fee": fee,
        "status": a.status,
        "due": due,
        "invoiced": invoiced,
    }
    entries.append(entry)
    save_board(path, entries)
    view = annotate(entry, today)
    if a.json:
        print(json.dumps({
            "tool": TOOL, "version": __version__, "command": "add",
            "board": path.name, "today": today.isoformat(),
            "cad_to_inr": cad_to_inr,
            "deal": _entry_json(view, cad_to_inr),
        }, indent=2))
    else:
        print(f"Added deal #{entry['id']}: {entry['brand']} — "
              f"{entry['deliverable']} — "
              f"{_fmt_money(fee, cad_to_inr)} "
              f"(status {entry['status']}"
              + (f", deliverable due {due}" if due else "")
              + (f", invoiced {invoiced}" if invoiced else "")
              + ")")
        print(f"Board: {path.name} ({len(entries)} deal(s))")
    return 0


def cmd_list(a):
    cad_to_inr = _cad_to_inr(a)
    path = Path(a.board)
    entries = load_board(path)
    today = today_arg(a.today)
    annotated = [annotate(e, today) for e in entries]
    totals = compute_totals(entries)
    if a.json:
        print(json.dumps(list_as_json(annotated, totals, path.name,
                                      today, cad_to_inr), indent=2))
    else:
        print(render_list_text(annotated, totals, path.name, today,
                               cad_to_inr))
    return 0


def cmd_due(a):
    cad_to_inr = _cad_to_inr(a)
    path = Path(a.board)
    entries = load_board(path)
    today = today_arg(a.today)
    due_view = build_due(entries, today)
    totals = compute_totals(entries)
    if a.json:
        print(json.dumps(due_as_json(due_view, totals, path.name,
                                     today, cad_to_inr), indent=2))
    else:
        print(render_due_text(due_view, totals, path.name, today,
                              cad_to_inr))
    return 1 if action_count(due_view) else 0


def cmd_move(a):
    cad_to_inr = _cad_to_inr(a)
    path = Path(a.board)
    entries = load_board(path)
    today = today_arg(a.today)
    entry = find_entry(entries, a.id)
    old = entry["status"]
    new = a.status
    if old in TERMINAL:
        raise ToolError(f"deal #{a.id} is {old} — '{old}' is a "
                        f"terminal status and the deal cannot be "
                        f"moved out of it")
    if new == old:
        raise ToolError(f"deal #{a.id} is already {old}")
    if new not in TRANSITIONS[old]:
        allowed = ", ".join(TRANSITIONS[old])
        raise ToolError(f"deal #{a.id} cannot move from {old} to "
                        f"{new} — from {old} it can move to: "
                        f"{allowed}")
    entry["status"] = new
    stamped = False
    if new == "invoiced" and entry["invoiced"] is None:
        entry["invoiced"] = today.isoformat()
        stamped = True
    save_board(path, entries)
    totals = compute_totals(entries)
    view = annotate(entry, today)
    if a.json:
        print(json.dumps({
            "tool": TOOL, "version": __version__, "command": "move",
            "board": path.name, "today": today.isoformat(),
            "cad_to_inr": cad_to_inr,
            "deal": _entry_json(view, cad_to_inr),
            "totals": _totals_json(totals, cad_to_inr),
        }, indent=2))
    else:
        print(f"Deal #{entry['id']} moved {old} → {new}: "
              f"{entry['brand']} — {entry['deliverable']} — "
              f"{_fmt_money(entry['fee'], cad_to_inr)}")
        if stamped:
            print(f"Invoice date recorded as {entry['invoiced']} — "
                  f"the payment-aging clock starts from there.")
        for line in _totals_lines(totals, cad_to_inr):
            print(line)
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    _JsonAwareParser.json_mode = "--json" in argv
    ap = _JsonAwareParser(
        prog=TOOL,
        description="A local brand-deal board for creators: what "
                    "is due, what is delivered-but-unpaid, and "
                    "which invoices are aging (stdlib only, local "
                    "only).")
    sub = ap.add_subparsers(dest="command", required=True,
                            parser_class=_JsonAwareParser)

    p_add = sub.add_parser(
        "add", help="add a deal to the board (creates the board "
                    "file on first add)")
    p_add.add_argument("--brand", required=True,
                       help="the brand the deal is with")
    p_add.add_argument("--contact", default="",
                       help="who you deal with there")
    p_add.add_argument("--deliverable", required=True,
                       help="what you owe them")
    p_add.add_argument("--fee", type=float, required=True,
                       help="agreed fee in CAD (>= 0)")
    p_add.add_argument("--status", choices=STATUSES,
                       default="pitched",
                       help="pipeline stage (default pitched)")
    p_add.add_argument("--due", default=None,
                       help="deliverable due date, YYYY-MM-DD")
    p_add.add_argument("--invoiced", default=None,
                       help="invoice date, YYYY-MM-DD (required "
                            "information once a deal is invoiced or "
                            "paid; defaults to today for those "
                            "statuses)")
    _today_arg(p_add)
    _board_arg(p_add)
    _json_arg(p_add)
    _inr_arg(p_add)
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser(
        "list", help="every deal on the board, plus the money "
                     "totals")
    _today_arg(p_list)
    _board_arg(p_list)
    _json_arg(p_list)
    _inr_arg(p_list)
    p_list.set_defaults(func=cmd_list)

    p_due = sub.add_parser(
        "due", help="the work view: deliverables due, delivered "
                    "work not yet invoiced, and unpaid invoices "
                    "aging — each with a line to send; exit 1 when "
                    "anything needs action")
    _today_arg(p_due)
    _board_arg(p_due)
    _json_arg(p_due)
    _inr_arg(p_due)
    p_due.set_defaults(func=cmd_due)

    p_move = sub.add_parser(
        "move", help="move a deal to a new pipeline status "
                     "(paid and dead are terminal)")
    p_move.add_argument("id", type=int, help="deal id (see `list`)")
    p_move.add_argument("status", choices=STATUSES,
                        help="the new status")
    _today_arg(p_move)
    _board_arg(p_move)
    _json_arg(p_move)
    _inr_arg(p_move)
    p_move.set_defaults(func=cmd_move)

    a = ap.parse_args(argv)

    def fail(msg):
        if getattr(a, "json", False):
            print(json.dumps({"error": msg}))
        else:
            print(f"ERROR: {msg}")
        return 2

    try:
        return a.func(a)
    except ToolError as exc:
        return fail(str(exc))


if __name__ == "__main__":
    sys.exit(main())
