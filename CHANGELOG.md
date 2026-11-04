# Changelog

## v0.2.0 — 2026-11-04

The Usage-Rights Expiry fold: the board now tracks the usage
window each deal grants the brand, not just the money.

- **New `rights` command — the usage-rights view.** Four
  groups against an explicit `--as-of` date (the pack's
  `--today` convention under the name the question is asked
  with; `--today` is accepted as the same flag): **expired**
  (window closed), **expiring within 30 days**, **active**,
  and **no expiry recorded**. The expiry date is the **last
  day** of the window — on that day the deal is expiring with
  0 days left, and it turns expired the next day; day 30
  counts as expiring, day 31 is active. Exits **1 when any
  window is expired or closing**, so a reminder script can
  act on it; 0 otherwise.
- **Three optional board fields** — `usage_start`,
  `usage_months`, `usage_expires` — validated like every
  other field, with errors that name the entry and the field
  (a `usage_months` with no `usage_start` to count from, and
  an expiry before its start, are clean errors, never
  tracebacks). A recorded `usage_expires` rules; with only a
  start and a length, the end is computed (start + months,
  the day clamped to the target month's length) and labelled
  **computed** wherever it appears. `add` takes
  `--usage-start` / `--usage-months` / `--usage-expires`.
  Boards written by v0.1.0 load unchanged — old deals simply
  have no window recorded.
- **No expiry is ever invented.** Deals without usage fields
  land in NO EXPIRY RECORDED — unknown, not unlimited — and
  the tool never derives an expiry from the deliverable or
  invoice date, which say nothing about usage.
- **Renewal money, kept honest.** Per-group counts and
  values, a per-brand roll-up, and one "renewal value at
  stake" figure (expired + expiring). Expired and expiring
  deals get a polite renewal line built only from board
  facts (brand, contact, deliverable, dates) — it **never
  names a renewal price**, because the board records the
  original fee, not a renewal fee.
- Sample board extended: the same nine deals with the same
  v0.1.0 totals (delivered-but-unpaid still $4,850 against
  $650 paid) — three deals now carry usage terms, one in
  each dated group (expired $2,000 · expiring $1,750 ·
  active $1,100), and the other six sit in NO EXPIRY
  RECORDED ($5,800), so renewal value at stake is $3,750.
- 77 tests (28 new): hand-computed window boundaries
  (expiry day itself, day 30 in / day 31 active), month
  clamping including leap years, recorded-over-computed
  precedence, corrupt usage-field errors, `add`-flag
  validation, renewal-line fact checks (including a ban on
  naming a price), text/JSON agreement, and the sample
  board's hand-derived buckets. Zero v0.1.0 regressions —
  the `due` view's output is unchanged apart from the
  version banner.

## v0.1.0 — 2026-11-04

First release.

- **One local JSON board of brand deals** — brand, contact,
  deliverable, fee (CAD), status (`pitched`/`negotiating`/
  `agreed`/`delivered`/`invoiced`/`paid`/`dead`), deliverable
  due date and invoice date. Created by the first `add`;
  validated on every read with errors that name the offending
  entry. A corrupt board is a clean error and is **never
  overwritten or silently wiped**; saves are atomic (temp file
  + replace).
- **Validated stage moves** — `move <id> <status>` walks a
  deal one stage at a time (`negotiating` may step back to
  `pitched`, any live deal may be marked `dead`). **`paid` and
  `dead` are terminal**: moving out of them, skipping a stage,
  or moving to the current status are all clean errors. Moving
  to `invoiced` stamps the invoice date with today if none is
  recorded — that date starts the payment-aging clock.
- **`due` — the work view** — four action groups, oldest /
  most overdue first: **deliverables** of agreed deals overdue
  or due within 7 days (day 7 counts, day 8 does not),
  **delivered work never invoiced**, unpaid invoices at
  **30+ days (overdue)** and **14–29 days (to chase)**. Exits
  **1 when anything needs action**, so a reminder script can
  act on it; 0 when the board is quiet.
- **Lines built only from board facts** — deliverables and
  invoices each get a polite, copy-ready message naming the
  brand, contact, deliverable, fee and the real dates. No
  invented payment terms (never "net-30"), no late fees, no
  fake urgency. Delivered-uninvoiced deals get a next step for
  the creator instead: send the invoice.
- **Honest totals everywhere** — pipeline value by status,
  money delivered-but-unpaid (delivered + invoiced), and money
  paid, as three separate numbers. Only `paid` is income.
- **`--cad-to-inr RATE`** — also prints INR equivalents next to
  every amount (the CAD + INR display pattern of payout-tracker).
- **`--json` on every command** — one JSON object with the same
  numbers and exit codes as the text view; errors are
  `{"error": ...}` objects, argparse usage errors included.
- **`--today YYYY-MM-DD`** pins the date for reproducible runs
  and reminder scripts.
- **`SKILL.md`** at the repo root for AI coding agents:
  commands, the JSON schemas, exit codes, and the honesty
  rules (paid is the only income; a move records what really
  happened; message lines state board facts only).
- Bundled sample board (`examples/sample-board.json`): nine
  deals, one in every stage — including an agreed deliverable
  5 days overdue, a delivered deal never invoiced, and an
  invoice 37 days unpaid — with $4,850 delivered-but-unpaid
  against $650 paid.
- 49 stdlib-unittest tests: hand-computed deliverable-window
  and invoice-aging boundaries on a fixed `--today`, terminal
  and stage-skip move errors, the full pitched→paid walk with
  invoice-date stamping, corrupt-board safety (file left
  byte-identical), message-fact checks (including a ban on
  invented terms), hand-added totals, and JSON/text agreement.
- Pure Python standard library; local only; MIT licence.
