# Contributing

Contributions are welcome — bug reports, fixes and small focused features.

## Ground rules

- **Standard library only.** brand-deal-pipeline's promise is
  "clone and run". Pull requests that add a third-party dependency
  will not be merged.
- **Local only.** No network calls, no telemetry, no uploads of
  user files. The tool tracks and drafts — it never sends
  messages for the user.
- **The board is the user's livelihood data.** A change that can
  lose, corrupt or silently rewrite board entries will not be
  merged. Loading must keep validating every entry; saving must
  stay atomic; a corrupt board must stay an error, never a wipe.
- **The pipeline stays honest.** Stage transitions and the
  terminal statuses (`paid`, `dead`) are a stated product
  choice, as are the work-view boundaries (7-day deliverable
  window, 14-day chase, 30-day overdue). Changing any of them is
  a behaviour change: it needs the README tables, the changelog,
  the SKILL.md schema and the boundary tests updated together.
- **Message lines state board facts only.** No urgency, payment
  term or deadline wording may enter the suggested lines unless
  it comes from a field on the board. Tests assert the absence
  of invented terms like "net-30" and fake-urgency phrasing —
  keep them passing.
- **Both directions tested.** A behaviour change needs a test
  where good input succeeds and bad input fails cleanly — not
  just one side. Date math needs hand-computed ages against a
  fixed `--today`, not ages copied from the tool's own output.

## Getting started

```bash
git clone https://github.com/jasveerai88/brand-deal-pipeline
cd brand-deal-pipeline
python3 -m unittest discover -s tests -v
python3 src/brand_deal_pipeline.py due --board examples/sample-board.json \
    --today 2026-11-04
```

## Pull requests

1. Fork, branch, and keep the change to one topic.
2. Add or update tests under `tests/`; the full suite must pass.
3. Note the change in `CHANGELOG.md` under an "Unreleased" heading.
4. Describe the behaviour change with a real before/after run if
   the CLI output changes.
