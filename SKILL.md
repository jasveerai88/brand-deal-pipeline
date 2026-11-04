---
name: brand-deal-pipeline
description: Track brand deals on one local JSON board — brand, contact, deliverable, fee (CAD), pipeline status, deliverable due date, invoice date — and surface the work view: deliverables overdue or due within 7 days, delivered work that was never invoiced, and unpaid invoices aging into CHASE (14+ days) and OVERDUE (30+), each with a polite, fact-only line to send, plus honest totals (pipeline value by status, delivered-but-unpaid, paid). Also track each deal's usage-rights window (usage_start / usage_months / usage_expires) and surface the rights view: windows expired, expiring within 30 days, active, or with no expiry recorded — the last always reported as unknown, never guessed — with renewal value at stake and fact-only renewal lines that never name a renewal price. Use when a creator juggles sponsorships across DMs and spreadsheets and agency CRMs are overkill. Exit 1 from `due` or `rights` means action items exist — it is a finding, not a failure.
---

# brand-deal-pipeline — agent skill

## Purpose

A brand deal is not done when the brand says yes — it is done
when the creator is paid. Deals die in the gap: a deliverable
date slips past unnoticed, delivered work never gets invoiced,
an invoice ages in someone's inbox. This tool keeps one local
JSON board of deals and answers, on demand: what is due, what
is delivered-but-unpaid, and which invoices need chasing today.
It also answers the question that comes after payment: how
long may the brand keep using the content? Each deal can
record a usage window, and the `rights` view shows which
windows have closed, which are closing, and which deals never
recorded one. Pure Python standard library; local only; the
board file is the only thing it reads or writes.

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
- A creator grants usage rights with their content and wants
  the renewal dates tracked — read `rights` to brief which
  windows closed or are closing and what value is at stake.

Do NOT use when:
- A team needs shared access, roles, approvals or automatic
  sending — that is a CRM's job; this tool tracks and drafts,
  it never sends.
- Deals are in multiple currencies — the board is CAD (INR
  figures are display equivalents only, via `--cad-to-inr`).

## Commands

Every command takes `--board FILE` (default `deals.json`) and
`--json`. Commands also take `--cad-to-inr RATE`; view/mutation
commands take `--today YYYY-MM-DD` to pin the date (`rights`
pins with `--as-of`, same value).

```bash
# Add a deal (creates the board on first add); usage terms
# are optional — record them when the deal grants them
python3 src/brand_deal_pipeline.py add --brand "Summit Outdoor Co" \
    --contact "Casey Lin" --deliverable "Winter gear roundup" \
    --fee 1750 [--status pitched] [--due 2026-09-20] \
    [--invoiced 2026-09-28] [--usage-start 2026-08-01] \
    [--usage-months 3] [--usage-expires 2026-11-20]

# The work view (exit 1 if anything needs action)
python3 src/brand_deal_pipeline.py due [--today 2026-11-04]

# The usage-rights view (exit 1 if a window is expired or
# closing within 30 days)
python3 src/brand_deal_pipeline.py rights [--as-of 2026-11-04]

# Everything on the board, with totals
python3 src/brand_deal_pipeline.py list

# Move a deal along the pipeline
python3 src/brand_deal_pipeline.py move 7 paid
```

Board entries: `id` (assigned by `add`), `brand` (required),
`contact` (may be empty), `deliverable` (required), `fee` (CAD,
≥ 0, required), `status` (see below), `due` (YYYY-MM-DD or
null), `invoiced` (YYYY-MM-DD or null — required once a deal is
`invoiced` or `paid`), and the optional usage fields
`usage_start` (YYYY-MM-DD or null), `usage_months` (whole
months ≥ 1 or null — needs a `usage_start` to count from) and
`usage_expires` (YYYY-MM-DD or null). The board is validated
on every read; a corrupt board is a clean error and is never
overwritten. Boards written before the usage fields existed
load unchanged — their deals simply have no usage window
recorded.

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

## The rights view (boundaries are exact)

A deal's usage window is judged against `--as-of` (default:
today; `--today` is accepted as the same flag). The effective
expiry: a recorded `usage_expires` rules; otherwise
`usage_start + usage_months` is computed (day clamped to the
target month's length) and labelled `expiry_source:
"computed"`. **The expiry date is the last day of the
window** — the brand may use the content through that day.

| Group | Rule | JSON key |
|---|---|---|
| Expired | expiry date before the as-of date | `expired` |
| Expiring | expiry is the as-of date itself (0 days left) up to exactly 30 days out (day 30 in) | `expiring` |
| Active | expiry 31+ days out (day 31 out of expiring) | `active` |
| No expiry recorded | no recorded expiry and no start + months to compute one from | `no_expiry` |

Expired lists most-overdue first; expiring and active list
soonest expiry first; no-expiry lists by id. Expired and
expiring entries carry a renewal `message` (facts only — it
never names a price). `rights` exits 1 when the expired or
expiring group is non-empty, else 0. The view adds
`rights_totals`: per-group `{count, amount}`,
`renewal_at_stake` (expired + expiring amounts) and
`by_brand_at_stake` (the same money grouped by brand),
alongside the pipeline `totals`. Entries add `usage_expiry`
(the effective expiry or null), `expiry_source`
(`"recorded"` / `"computed"` / null), `state`, and signed
`days_left` (negative = days past expiry; null in the
no-expiry group).

## Output JSON schema (`--json`)

Common fields: `tool` (`"brand-deal-pipeline"`), `version`,
`command`, `board` (file name), `cad_to_inr` (rate or null);
`due`/`list`/`add`/`move` add `today`; `rights` adds `as_of`.

Entry objects: `id`, `brand`, `contact`, `deliverable`, `fee`,
`status`, `due`, `invoiced`, `usage_start`, `usage_months`,
`usage_expires`, plus computed `days_until_due`
(null without a due date) and `invoice_age_days` (only for
`invoiced` deals). Due-view entries add `state`
(`"overdue"`/`"due_soon"` for deliverables, `"chase"`/`"overdue"`
for invoices), `days` (days late/left or invoice age), and
`message` or `next_step`. With `--cad-to-inr`, money fields
gain `*_inr` siblings.

`due`: the four group arrays above, `current_invoices` and
`future_deliverables` counts, `action_items`, `totals`.
`rights`: the four group arrays (`expired`, `expiring`,
`active`, `no_expiry`), `action_items`, `rights_totals`,
`totals` — see the rights section above for entry fields.
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
  no invoice unpaid for 14+ days); for `rights`, no usage
  window is expired or closing within 30 days.
- `1` — `due` or `rights` only: at least one action item
  exists. This is the tool working — surface the items,
  oldest/most overdue first.
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
- **Exit 1 is a finding.** When `due` or `rights` exits 1,
  report the action items by brand and days; do not describe
  the board as "all clear".
- **Usage expiries are never invented.** No usage fields on a
  deal means the expiry is UNKNOWN: report the deal as
  no-expiry-recorded — never as "unlimited", never as
  "perpetual", and never derive an expiry from the due or
  invoice date, which say nothing about usage. A computed
  expiry (start + months) is a derivation, not a contract
  date: quote it as computed, with its start and months.
  Renewal lines never name a renewal price — the fee on the
  board is the original deal's fee, and presenting it as the
  price of a renewal would be inventing terms. `renewal_at_stake`
  is the value of the deals whose windows are closed or
  closing, not a quote and not income.
- Local only: the tool reads/writes only the board file named
  with `--board` and sends nothing anywhere.
