# brand-deal-pipeline

**The deal isn't done when they say yes — it's done when you're paid.**

Between "yes" and "paid" sits the part of a sponsorship nobody
posts about: the deliverable whose date quietly slipped past,
the video you delivered three weeks ago and never invoiced, the
invoice aging in a brand manager's inbox while you assume it's
"being processed". Creators track this in DMs and spreadsheets,
which is to say they don't track it — they rediscover it, late.
Agency CRMs fix it for teams: monthly subscriptions, pipeline
boards and fields built for account managers, not for one
creator with nine deals.

`brand-deal-pipeline` is one JSON board file and five commands.
It walks every deal from **pitched** to **paid**, and its `due`
view is the morning checklist: which deliverables are due or
overdue, which delivered work was never invoiced, and which
invoices are aging — each with a polite, copy-ready line built
only from the facts on the board. The totals stay honest:
pipeline value by status, money delivered-but-unpaid, and money
actually paid, kept in separate buckets where they belong.
And because delivered content keeps working for the brand long
after the invoice is paid, its `rights` view tracks the usage
window each deal granted: which windows have closed, which are
closing, and what renewal money is sitting on the table.

- Pure Python 3 standard library — no dependencies, no install step
- Local only — your deal list never leaves your machine
- Script-friendly exit codes: `0` = nothing needs action, `1` =
  action items exist (so a reminder script can act on it),
  `2` = error

## The pipeline

| Status | Meaning |
|---|---|
| `pitched` | You (or they) opened the conversation |
| `negotiating` | Terms are being worked out |
| `agreed` | Fee and deliverable settled — the work clock is running |
| `delivered` | The work is out — but no invoice yet |
| `invoiced` | Invoice sent — the payment clock is running |
| `paid` | Money in. Terminal |
| `dead` | Gone quiet or declined. Terminal |

Deals move forward one stage at a time (`negotiating` may step
back to `pitched`), and any live deal can be marked `dead`.
**`paid` and `dead` are terminal**: a deal cannot be moved out
of them, and skipping a stage (say, `agreed` straight to `paid`)
is a clean error that names the moves that *are* allowed.
Moving a deal to `invoiced` stamps the invoice date with today
if none is recorded — that date is what the aging clock runs
from, so the chase view is only as honest as the board.

## The work view

| Group | Rule |
|---|---|
| DELIVERABLES DUE | `agreed` deals overdue, or due within 7 days |
| DELIVERED — INVOICE NOT SENT YET | `delivered` deals — your move, not theirs |
| INVOICES OVERDUE | `invoiced` deals unpaid for 30+ days |
| INVOICES TO CHASE | `invoiced` deals unpaid for 14–29 days |

Boundaries are exact: a deliverable due in exactly 7 days is in
the view, 8 days is not; an invoice at 14 days is a chase, at
30 it is overdue.

## The rights view

A delivered video keeps earning for the brand after you've been
paid — that is what usage rights are: the window during which
the brand may keep using your content. When the window closes,
continued use is a renewal conversation, and creators who track
the dates get paid twice for the same work. The `rights` view
is that tracker:

| Group | Rule |
|---|---|
| USAGE RIGHTS EXPIRED | the window's last day is before the as-of date |
| EXPIRING WITHIN 30 DAYS | the last day is the as-of date itself, up to 30 days out |
| ACTIVE | the last day is 31+ days out |
| NO EXPIRY RECORDED | the board records no window end — unknown, not unlimited |

The expiry date is the **last day** of the window: on that day
the deal is expiring (0 days left); it is expired from the next
day. A deal records its window with any of `usage_start`,
`usage_months` (counted from the start) and `usage_expires`.
A recorded `usage_expires` rules; with only a start and a
length, the end is computed — start + months, the day clamped
to the target month's length (31 Jan + 1 month = 28 Feb) — and
labelled *computed* wherever it appears. Deals with no usage
fields land in NO EXPIRY RECORDED: the tool never derives an
expiry from the deliverable or invoice date, because those
dates say nothing about usage. Expired and expiring deals get
a polite renewal line built from board facts — brand, contact,
deliverable and the real dates — which never names a renewal
price: the board records the original fee, not a renewal fee.
`rights` exits 1 when any window is expired or closing within
30 days, 0 otherwise.

## The board file

One JSON file (default `deals.json`, created by your first
`add`; every command takes `--board FILE`):

```json
{"deals": [
  {"id": 7, "brand": "Summit Outdoor Co", "contact": "Casey Lin",
   "deliverable": "Winter gear roundup", "fee": 1750.0,
   "status": "invoiced", "due": "2026-09-20",
   "invoiced": "2026-09-28", "usage_expires": "2026-11-20"}
]}
```

| Field | Meaning |
|---|---|
| `id` | assigned by `add`, never reused |
| `brand` | the brand the deal is with (required) |
| `contact` | who you deal with there (may be empty) |
| `deliverable` | what you owe them (required) |
| `fee` | agreed fee in CAD (required, ≥ 0) |
| `status` | one of the seven stages above |
| `due` | deliverable due date, `YYYY-MM-DD`, or `null` |
| `invoiced` | invoice date, or `null` (required once invoiced/paid) |
| `usage_start` | day the brand's usage window opened, or `null` |
| `usage_months` | window length in whole months (≥ 1) from `usage_start`, or `null` |
| `usage_expires` | last day of the usage window, or `null` (rules over start + months) |

You can edit the file by hand — it is validated on every read.
A corrupt board is a clean error that names the problem entry,
and the file is **never** overwritten or silently wiped; writes
are atomic (temp file + replace), so a crash mid-save cannot
leave you half a board.

## The lines it writes

Every deliverable and invoice in the work view gets a
ready-to-send message built **only** from facts on the board —
the brand, the contact, the deliverable, the fee and the real
dates. Nothing is invented: no payment terms the board doesn't
record (the tool will never write "net-30" for you), no late
fees, no fake urgency:

> Hi Casey Lin, following up again on the invoice for Winter
> gear roundup ($1,750.00) for Summit Outdoor Co, sent on
> 2026-09-28 — 37 days ago now. If anything is missing from my
> side to process it, I'm happy to send it over; otherwise I'd
> appreciate an update on when it will be paid.

Delivered-but-uninvoiced deals get a note to *you* instead —
the brand can't pay an invoice that doesn't exist:

> Send the invoice for this deal ($2,000.00) (deliverable was
> due 2026-10-25) — the work is delivered, and the payment
> clock only starts once the invoice is out.

## Usage

```bash
# 1. Add a deal (creates the board on first add)
python3 src/brand_deal_pipeline.py add --brand "Summit Outdoor Co" \
    --contact "Casey Lin" --deliverable "Winter gear roundup" \
    --fee 1750 --due 2026-09-20

# 2. The work view: what needs action today, with the lines
python3 src/brand_deal_pipeline.py due \
    --board examples/sample-board.json --today 2026-11-04

# 3. See everything, with the totals
python3 src/brand_deal_pipeline.py list \
    --board examples/sample-board.json --today 2026-11-04

# 4. Walk a deal along the pipeline as stages really change
python3 src/brand_deal_pipeline.py move 7 delivered \
    --board examples/sample-board.json
python3 src/brand_deal_pipeline.py move 7 invoiced \
    --board examples/sample-board.json
python3 src/brand_deal_pipeline.py move 7 paid \
    --board examples/sample-board.json

# 5. Also print INR equivalents (rate per 1 CAD dollar)
python3 src/brand_deal_pipeline.py due \
    --board examples/sample-board.json --today 2026-11-04 \
    --cad-to-inr 67.97

# 6. Drive a reminder: exit 1 means something needs action
python3 src/brand_deal_pipeline.py due || echo "check the board"

# 7. The rights view: which usage windows have closed or are
#    closing — record terms with add --usage-start 2026-08-01
#    --usage-months 3 (or --usage-expires 2026-11-20)
python3 src/brand_deal_pipeline.py rights \
    --board examples/sample-board.json --as-of 2026-11-04
```

`--today YYYY-MM-DD` pretends today is that date — the bundled
sample uses fixed dates, so its demos pass `--today 2026-11-04`
to stay reproducible. Day to day you omit it and the real date
is used. `rights` takes `--as-of` for the same job, under the
name the question is asked with (it also accepts `--today`).

## Use with AI agents

Every command takes `--json`: one JSON object with the same
numbers and exit codes as the text view (errors come back as
`{"error": ...}`):

```bash
python3 src/brand_deal_pipeline.py due \
    --board examples/sample-board.json --today 2026-11-04 --json
```

Agents: read [SKILL.md](SKILL.md) first — commands, the full
JSON schemas, exit codes, and the honesty rules (only `paid`
is income; message lines may only state facts from the board).

## Real run (verbatim)

The bundled sample board holds nine deals for one creator —
one in every stage, including an agreed deliverable already
overdue and an invoice 37 days unpaid. Against
`--today 2026-11-04`:

```text
$ python3 src/brand_deal_pipeline.py due --board examples/sample-board.json --today 2026-11-04
brand-deal-pipeline v0.2.0 — due · board sample-board.json · today 2026-11-04
Amounts in CAD.

DELIVERABLES DUE — agreed deals overdue or due within 7 days (2):
#4 · Kelowna Dental Studio (Dr. Sam Whitaker) — Clinic tour reel — $900.00 — agreed — deliverable due 2026-10-30 (5 days overdue)
   → Hi Dr. Sam Whitaker, a quick update on the Clinic tour reel for Kelowna Dental Studio ($900.00): it was due on 2026-10-30, 5 days ago. It is still in progress on my side — I'll confirm a revised delivery date as soon as I have one, and I'm sorry for the slip.
#3 · Brightpath Tutoring (Priya Nair) — Sponsored tutorial video — $1,500.00 — agreed — deliverable due 2026-11-09 (due in 5 days)
   → Hi Priya Nair, confirming the Sponsored tutorial video for Brightpath Tutoring ($1,500.00) is due on 2026-11-09 — 5 days from now. I'll send it over as soon as it is ready.

DELIVERED — INVOICE NOT SENT YET (1):
#5 · Harbour Lights Hotels (Alex Romero) — Weekend getaway feature — $2,000.00 — delivered — deliverable due 2026-10-25
   → Send the invoice for this deal ($2,000.00) (deliverable was due 2026-10-25) — the work is delivered, and the payment clock only starts once the invoice is out.

INVOICES OVERDUE — unpaid for 30+ days (1):
#7 · Summit Outdoor Co (Casey Lin) — Winter gear roundup — $1,750.00 — invoiced — deliverable due 2026-09-20 — invoiced 2026-09-28 (invoice out 37 days)
   → Hi Casey Lin, following up again on the invoice for Winter gear roundup ($1,750.00) for Summit Outdoor Co, sent on 2026-09-28 — 37 days ago now. If anything is missing from my side to process it, I'm happy to send it over; otherwise I'd appreciate an update on when it will be paid.

INVOICES TO CHASE — unpaid for 14+ days (1):
#6 · Pinecrest Supplements (Taylor Brooks) — Product review video — $1,100.00 — invoiced — deliverable due 2026-10-12 — invoiced 2026-10-20 (invoice out 15 days)
   → Hi Taylor Brooks, following up on the invoice for Product review video ($1,100.00) for Pinecrest Supplements, sent on 2026-10-20 — 15 days ago. Could you let me know whether it is in the payment queue, or if you need anything else from me to process it?

TOTALS by status: pitched $750.00 (1) · negotiating $1,200.00 (1) · agreed $2,400.00 (2) · delivered $2,000.00 (1) · invoiced $2,850.00 (2) · paid $650.00 (1) · dead $800.00 (1)
Delivered but unpaid: $4,850.00 · Paid: $650.00
Action items: 5 · Invoices still current (< 14 days): 0 · Deliverables further out (> 7 days): 0
(exit code: 1 — five action items)
```

Read what the board is really saying: the pipeline holds
$9,200 of live deals, but only $650 has actually landed.
$4,850 of it is work already done and money still owed — and
$1,750 of that has been sitting unpaid for 37 days. That gap
between "deals on the board" and "paid" is exactly the gap
this tool exists to close.

The same board through the rights view, against the same
fixed date:

```text
$ python3 src/brand_deal_pipeline.py rights --board examples/sample-board.json --as-of 2026-11-04
brand-deal-pipeline v0.2.0 — rights · board sample-board.json · as of 2026-11-04
Amounts in CAD.

USAGE RIGHTS EXPIRED — the window has closed; content still in use past it is unpaid use (1):
#5 · Harbour Lights Hotels (Alex Romero) — Weekend getaway feature — $2,000.00 — delivered — deliverable due 2026-10-25 — usage expired 2026-11-01 (3 days ago; from 2026-08-01 + 3 months)
   → Hi Alex Romero, a note on the Weekend getaway feature for Harbour Lights Hotels: the usage window on our deal closed on 2026-11-01 — 3 days ago. If the content is still in use on your side, I'd like to agree a renewal covering the time since then; if it has been retired, no action is needed. Happy to talk it through either way.

EXPIRING WITHIN 30 DAYS — time to open the renewal conversation (1):
#7 · Summit Outdoor Co (Casey Lin) — Winter gear roundup — $1,750.00 — invoiced — deliverable due 2026-09-20 — invoiced 2026-09-28 — usage expires 2026-11-20 (in 16 days; recorded)
   → Hi Casey Lin, a note on the Winter gear roundup for Summit Outdoor Co: the usage window on our deal runs until 2026-11-20 — 16 days from now. If you'd like to keep using the content past that date, I'm glad to agree an extension before the window lapses.

ACTIVE — window open beyond 30 days (1):
#6 · Pinecrest Supplements (Taylor Brooks) — Product review video — $1,100.00 — invoiced — deliverable due 2026-10-12 — invoiced 2026-10-20 — usage expires 2027-10-12 (in 342 days; from 2026-10-12 + 12 months)

NO EXPIRY RECORDED — the board does not say when usage ends; that is unknown, not unlimited (6):
#1 · Northwind Coffee (Maya Chen) — 60-second product reel — $750.00 — pitched — no usage expiry recorded
#2 · Trailhead Gear (Jordan Blake) — Unboxing short + story set — $1,200.00 — negotiating — deliverable due 2026-11-20 — no usage expiry recorded
#3 · Brightpath Tutoring (Priya Nair) — Sponsored tutorial video — $1,500.00 — agreed — deliverable due 2026-11-09 — no usage expiry recorded
#4 · Kelowna Dental Studio (Dr. Sam Whitaker) — Clinic tour reel — $900.00 — agreed — deliverable due 2026-10-30 — no usage expiry recorded
#8 · Meadowbrook Farms (Robin Adeyemi) — Farm-to-table short — $650.00 — paid — deliverable due 2026-09-10 — invoiced 2026-09-15 — no usage expiry recorded
#9 · Old Mill Bakery (June Park) — Holiday campaign short — $800.00 — dead — no usage expiry recorded

RIGHTS TOTALS: expired $2,000.00 (1) · expiring $1,750.00 (1) · active $1,100.00 (1) · no expiry recorded $5,800.00 (6)
Renewal value at stake (expired + expiring): $3,750.00
By brand (expired + expiring): Harbour Lights Hotels $2,000.00 · Summit Outdoor Co $1,750.00
TOTALS by status: pitched $750.00 (1) · negotiating $1,200.00 (1) · agreed $2,400.00 (2) · delivered $2,000.00 (1) · invoiced $2,850.00 (2) · paid $650.00 (1) · dead $800.00 (1)
Delivered but unpaid: $4,850.00 · Paid: $650.00
Action items: 2 (usage expired or expiring within 30 days)
(exit code: 1 — one window closed, one closing)
```

Read the rights view the same way: only three of the nine
deals have a usage window recorded at all. One has already
closed — $2,000 of content the brand may still be running
unpaid — and one closes in 16 days, so $3,750 of renewal
value is on the table right now. The other six deals say
nothing about usage, and the view keeps them in their own
bucket: unknown is not unlimited, and it is never a date
the tool made up.

One deal's full walk, verbatim:

```text
$ python3 src/brand_deal_pipeline.py add --board /tmp/demo-deals.json --brand "Harbour Roast Coffee" --contact "Maya Chen" --deliverable "Launch reel" --fee 800 --due 2026-11-10 --today 2026-11-04
Added deal #1: Harbour Roast Coffee — Launch reel — $800.00 (status pitched, deliverable due 2026-11-10)
Board: demo-deals.json (1 deal(s))

$ python3 src/brand_deal_pipeline.py move 1 agreed --board /tmp/demo-deals.json --today 2026-11-04
Deal #1 moved pitched → agreed: Harbour Roast Coffee — Launch reel — $800.00
TOTALS by status: pitched $0.00 (0) · negotiating $0.00 (0) · agreed $800.00 (1) · delivered $0.00 (0) · invoiced $0.00 (0) · paid $0.00 (0) · dead $0.00 (0)
Delivered but unpaid: $0.00 · Paid: $0.00

$ python3 src/brand_deal_pipeline.py move 1 delivered --board /tmp/demo-deals.json --today 2026-11-09
Deal #1 moved agreed → delivered: Harbour Roast Coffee — Launch reel — $800.00
TOTALS by status: pitched $0.00 (0) · negotiating $0.00 (0) · agreed $0.00 (0) · delivered $800.00 (1) · invoiced $0.00 (0) · paid $0.00 (0) · dead $0.00 (0)
Delivered but unpaid: $800.00 · Paid: $0.00

$ python3 src/brand_deal_pipeline.py move 1 invoiced --board /tmp/demo-deals.json --today 2026-11-09
Deal #1 moved delivered → invoiced: Harbour Roast Coffee — Launch reel — $800.00
Invoice date recorded as 2026-11-09 — the payment-aging clock starts from there.
TOTALS by status: pitched $0.00 (0) · negotiating $0.00 (0) · agreed $0.00 (0) · delivered $0.00 (0) · invoiced $800.00 (1) · paid $0.00 (0) · dead $0.00 (0)
Delivered but unpaid: $800.00 · Paid: $0.00

$ python3 src/brand_deal_pipeline.py due --board /tmp/demo-deals.json --today 2026-11-30
brand-deal-pipeline v0.2.0 — due · board demo-deals.json · today 2026-11-30
Amounts in CAD.

INVOICES TO CHASE — unpaid for 14+ days (1):
#1 · Harbour Roast Coffee (Maya Chen) — Launch reel — $800.00 — invoiced — deliverable due 2026-11-10 — invoiced 2026-11-09 (invoice out 21 days)
   → Hi Maya Chen, following up on the invoice for Launch reel ($800.00) for Harbour Roast Coffee, sent on 2026-11-09 — 21 days ago. Could you let me know whether it is in the payment queue, or if you need anything else from me to process it?

TOTALS by status: pitched $0.00 (0) · negotiating $0.00 (0) · agreed $0.00 (0) · delivered $0.00 (0) · invoiced $800.00 (1) · paid $0.00 (0) · dead $0.00 (0)
Delivered but unpaid: $800.00 · Paid: $0.00
Action items: 1 · Invoices still current (< 14 days): 0 · Deliverables further out (> 7 days): 0
(exit code: 1 — the invoice is 21 days out and unpaid)

$ python3 src/brand_deal_pipeline.py move 1 paid --board /tmp/demo-deals.json --today 2026-12-02
Deal #1 moved invoiced → paid: Harbour Roast Coffee — Launch reel — $800.00
TOTALS by status: pitched $0.00 (0) · negotiating $0.00 (0) · agreed $0.00 (0) · delivered $0.00 (0) · invoiced $0.00 (0) · paid $800.00 (1) · dead $0.00 (0)
Delivered but unpaid: $0.00 · Paid: $800.00
```

## Tests

```bash
python3 -m unittest discover -s tests -v
# Ran 77 tests — OK
```

The suite covers both directions: the deliverable window and
the invoice-aging boundaries are checked at the exact days
(7 in / 8 out; 13 current, 14 chase, 30 overdue) against a
fixed `--today`, with ages worked out by hand; terminal deals
are proven immovable, stage-skipping and same-status moves
error cleanly, and the full pitched→paid walk stamps the
invoice date; the sample board's totals match hand-added
numbers (agreed 2,400 · invoiced 2,850 · delivered-but-unpaid
4,850 · paid 650); message lines are checked to contain the
real brand, deliverable and amount with no placeholders and no
invented terms like "net-30"; a corrupt board errors cleanly
and is left byte-identical (and `add` refuses to wipe it); and
the JSON and text views are asserted to agree on totals,
groups and exit codes. The usage windows get the same
treatment: the expiry boundaries are checked at the exact days
(the expiry day itself is *expiring* with 0 days left, day 30
in / day 31 active), month arithmetic is pinned at the clamp
cases (31 Jan + 1 month = 28 Feb, leap years included), a
recorded expiry is proven to rule over a computed one, corrupt
usage fields error cleanly naming the entry and the field,
renewal lines are proven to name no price, and the sample
board's rights buckets match hand-derived assignments
(expired 2,000 · expiring 1,750 · active 1,100 · no-expiry
5,800 · renewal at stake 3,750).

## Internal use

This tool does a real job for its author: it is the deal board
for the author's own channels — every channel sponsorship deal
is added the day it is pitched, walked stage by stage as the
work and the invoice actually happen, and `due` is the
checklist that decides who gets chased. GitHub Sponsors
follow-ups are tracked on the same board until they land as
paid.

## Known limits

- One board, one creator: no per-user views, no team stages or
  approvals — deliberately. If you need account managers and
  automations, you have outgrown this tool and a CRM is
  honestly the answer.
- It reminds; it does not send. The lines are for you to copy
  into your own email or DMs — the tool has no accounts and
  sends nothing.
- The aging clock runs from the invoice date on the board.
  If a brand pays in parts, record it as it lands (split the
  deal or adjust the fee by hand-editing the board) — the tool
  does not do partial-payment bookkeeping.
- Amounts are CAD only (with optional INR display equivalents
  via `--cad-to-inr`); the board does not do multi-currency
  books.
- Usage windows are only as real as what is recorded. The tool
  never infers an expiry from a deliverable or invoice date; a
  deal with no usage fields sits in NO EXPIRY RECORDED until
  you record the terms. A computed window end (start + months)
  is a derivation with a stated rule — day clamped to the
  target month — not a date read from a contract.

## Privacy

What it touches: only the board file you point it at. What it
sends: nothing — there is no network code in this tool.

## Support

If this rescues one invoice that was about to age into
oblivion, consider sponsoring:
**https://github.com/sponsors/jasveerai88**

## Licence

MIT — see [LICENSE](LICENSE).
