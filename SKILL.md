---
name: brand-deal-pipeline
description: Track brand deals on one local JSON board — brand, contact, deliverable, fee (CAD), pipeline status, deliverable due date, invoice date — and surface the work view: deliverables overdue or due within 7 days, delivered work that was never invoiced, and unpaid invoices aging into CHASE (14+ days) and OVERDUE (30+), each with a polite, fact-only line to send, plus honest totals (pipeline value by status, delivered-but-unpaid, paid). Use when a creator juggles sponsorships across DMs and spreadsheets and agency CRMs are overkill. Exit 1 from `due` means action items exist — it is a finding, not a failure.
---

# brand-deal-pipeline — agent skill

## Purpose

A brand deal is not done when the brand says yes — it is done
when the creator is paid. Deals die in the gap: a deliverable
date slips past unnoticed, delivered work never gets invoiced,
an invoice ages in someone's inbox. This tool keeps one local
JSON board of deals and answers, on demand: what is due, what
is delivered-but-unpaid, and which invoices need chasing today.
Pure Python standard library; local only; the board file is the
only thing it reads or writes.

**The honesty core of this tool:** only the `paid` total is
money in. `agreed` is a promise, `delivered` + `invoiced` is
work done and money owed ("delivered but unpaid") — never
present a pipeline total, at any stage, as income.

## When to use / not use

Use when:
- A creator tracks sponsorships / brand deals and needs to know
  what needs action today.
- An agent maintains the board: add deals when they land, move
  them as stages change, read `due` to brief the creator.
- A reminder script needs a yes/no "is anything actionable?"
  signal (`due` exit code 1 = yes).

Do NOT use when:
- A team needs shared access, roles, approvals or automatic
  sending — that is a CRM's job; this tool tracks and drafts,
  it never sends.
- Deals are in multiple currencies — the board is CAD (INR
  figures are display equivalents only, via `--cad-to-inr`).

## Commands

Every command takes `--board FILE` (default `deals.json`) and
`--json`. Commands also take `--cad-to-inr RATE`; view/mutation
commands take `--today YYYY-MM-DD` to pin the date.

```bash
# Add a deal (creates the board on first add)
python3 src/brand_deal_pipeline.py add --brand "Summit Outdoor Co" \
    --contact "Casey Lin" --deliverable "Winter gear roundup" \
    --fee 1750 [--status pitched] [--due 2026-09-20] \
    [--invoiced 2026-09-28]

# The work view (exit 1 if anything needs action)
python3 src/brand_deal_pipeline.py due [--today 2026-11-04]

# Everything on the board, with totals
python3 src/brand_deal_pipeline.py list

# Move a deal along the pipeline
python3 src/brand_deal_pipeline.py move 7 paid
```

Board entries: `id` (assigned by `add`), `brand` (required),
`contact` (may be empty), `deliverable` (required), `fee` (CAD,
≥ 0, required), `status` (see below), `due` (YYYY-MM-DD or
null), `invoiced` (YYYY-MM-DD or null — required once a deal is
`invoiced` or `paid`). The board is validated on every read; a
corrupt board is a clean error and is never overwritten.

## Statuses and transitions

Stages flow: `pitched` → `negotiating` → `agreed` → `delivered`
→ `invoiced` → `paid`. `negotiating` may step back to `pitched`;
any live deal may be marked `dead`. **`paid` and `dead` are
terminal** — moving out of them is a clean error, as is skipping
a stage (e.g. `agreed` → `paid`). Moving to `invoiced` stamps
the invoice date with today if none is recorded; that date is
what the payment-aging clock runs from.

## The work view (boundaries are exact)

Age and windows are whole days against `--today`.

| Group | Rule | JSON key |
|---|---|---|
| Deliverables due | status `agreed`, due date overdue or ≤ 7 days away (day 7 in, day 8 out) | `deliverables` |
| Delivered, not invoiced | status `delivered` | `delivered_uninvoiced` |
| Invoices to chase | status `invoiced`, invoice 14–29 days old (day 14 in) | `invoices_chase` |
| Invoices overdue | status `invoiced`, invoice 30+ days old (day 30 in) | `invoices_overdue` |

Inside a group: deliverables list most-overdue first, then
soonest due; invoices list oldest first. Deliverable and invoice
entries carry a `message` (the line to send); delivered entries
carry a `next_step` (the action is the creator's: send the
invoice).

## Output JSON schema (`--json`)

Common fields: `tool` (`"brand-deal-pipeline"`), `version`,
`command`, `board` (file name), `cad_to_inr` (rate or null);
`due`/`list`/`add`/`move` add `today`.

Entry objects: `id`, `brand`, `contact`, `deliverable`, `fee`,
`status`, `due`, `invoiced`, plus computed `days_until_due`
(null without a due date) and `invoice_age_days` (only for
`invoiced` deals). Due-view entries add `state`
(`"overdue"`/`"due_soon"` for deliverables, `"chase"`/`"overdue"`
for invoices), `days` (days late/left or invoice age), and
`message` or `next_step`. With `--cad-to-inr`, money fields
gain `*_inr` siblings.

`due`: the four group arrays above, `current_invoices` and
`future_deliverables` counts, `action_items`, `totals`.
`list`: `deals` (all entries by id), `totals`.
`add`: `deal` (the new entry). `move`: `deal` (updated) +
`totals`.
`totals`: `by_status` (each status `{count, amount}`),
`delivered_unpaid` (delivered + invoiced amounts), `paid`.

On error, stdout is a single object: `{"error": "<message>"}`
(board validation errors name the entry: `"entry 2: ..."`) with
exit code 2 — including argparse usage errors in `--json` mode.
Never plain text, never a traceback.

## Exit codes

- `0` — command succeeded; for `due`, nothing needs action (no
  deliverable due within 7 days, nothing delivered-uninvoiced,
  no invoice unpaid for 14+ days).
- `1` — `due` only: at least one action item exists. This is
  the tool working — surface the items, oldest/most overdue
  first.
- `2` — ERROR: board missing (for read/move commands), board
  corrupt (file left untouched), unknown id, an illegal move
  (terminal status, skipped stage, same status), invalid
  date/fee/flag. No board change was made; do not quote numbers
  from a failed run.

## Limits & honesty rules the agent must respect

- **Paid is the only income.** Report `totals.paid` as money
  in, `totals.delivered_unpaid` as work done and money owed,
  and every earlier stage as pipeline — a promise, not a
  result. An agreed fee that never gets delivered, invoiced
  and chased is how creators quietly work for free.
- **Message lines contain only board facts.** The suggested
  `message` names the brand, contact, deliverable, fee and the
  real dates — nothing else. Never edit in payment terms the
  board does not record (no "net-30", no late fees, no "final
  notice"), and never add urgency the facts do not carry. If
  you draft your own line instead, hold it to the same rule.
- **Moves record what really happened.** Run `move` when the
  stage actually changed — the deliverable really went out,
  the invoice really was sent. The invoice date starts the
  aging clock; backdating or fudging it falsifies every later
  chase decision.
- **Terminal is terminal.** A `paid` or `dead` deal never
  re-enters the pipeline. If a dead brand comes back, that is
  a new deal — `add` it; do not resurrect the old entry.
- **Exit 1 is a finding.** When `due` exits 1, report the
  action items by brand and days; do not describe the board as
  "all clear".
- Local only: the tool reads/writes only the board file named
  with `--board` and sends nothing anywhere.
