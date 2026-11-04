#!/usr/bin/env python3
"""Tests for brand-deal-pipeline. Stdlib unittest only.

Run from the pack root:
    python3 -m unittest discover -s tests -v

The date math is checked against hand-computed values for a fixed
--today of 2026-11-04 — never against the tool's own output:
    due 2026-11-11 -> 7 days left  (due_soon, exact boundary)
    due 2026-11-12 -> 8 days left  (outside the window)
    due 2026-11-04 -> due today
    due 2026-11-03 -> 1 day overdue
    invoiced 2026-10-22 -> 13 days (still current)
    invoiced 2026-10-21 -> 14 days (CHASE, exact boundary)
    invoiced 2026-10-06 -> 29 days (CHASE)
    invoiced 2026-10-05 -> 30 days (OVERDUE, exact boundary)
Sample-board totals by hand: pitched 750 · negotiating 1,200 ·
agreed 1,500+900 = 2,400 · delivered 2,000 · invoiced
1,100+1,750 = 2,850 · paid 650 · dead 800 · delivered-but-unpaid
2,000+2,850 = 4,850.
Both directions are covered: quiet boards exit 0, boards with
action items exit 1, and every broken input exits 2 with a clean
message — in text AND in --json mode — while a corrupt board file
is left byte-identical.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[1]
SRC = PACK_ROOT / "src" / "brand_deal_pipeline.py"
EXAMPLES = PACK_ROOT / "examples"
sys.path.insert(0, str(PACK_ROOT / "src"))

import brand_deal_pipeline as bd  # noqa: E402

TODAY = date(2026, 11, 4)
TODAY_S = "2026-11-04"


def entry(**over):
    base = {"id": 1, "brand": "Test Brand", "contact": "Test Person",
            "deliverable": "Test deliverable", "fee": 100.0,
            "status": "pitched", "due": None, "invoiced": None}
    base.update(over)
    return base


def run_cli(*args):
    return subprocess.run([sys.executable, str(SRC), *args],
                          capture_output=True, text=True)


class BoardCase(unittest.TestCase):
    """Base: a temp dir + helpers to write a board and run the CLI."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.board = Path(self.tmp.name) / "board.json"

    def tearDown(self):
        self.tmp.cleanup()

    def write_board(self, entries):
        self.board.write_text(json.dumps({"deals": entries}),
                              encoding="utf-8")
        return str(self.board)

    def cli(self, *args):
        return run_cli(*args, "--board", str(self.board))


class TestDeliverableWindow(unittest.TestCase):
    def test_boundaries_exact(self):
        cases = [
            ("2026-11-11", ("due_soon", 7)),   # exactly 7: in
            ("2026-11-12", None),              # 8: out
            ("2026-11-04", ("due_soon", 0)),   # due today
            ("2026-11-03", ("overdue", 1)),    # 1 day late
            ("2026-10-30", ("overdue", 5)),
            ("2026-12-25", None),              # far future
        ]
        for due, expected in cases:
            e = entry(status="agreed", due=due)
            self.assertEqual(bd.deliverable_state(e, TODAY), expected,
                             due)

    def test_only_agreed_deals_count(self):
        for status in ("pitched", "negotiating", "delivered",
                       "invoiced", "paid", "dead"):
            e = entry(status=status, due="2026-11-03",
                      invoiced="2026-09-01" if status in
                      ("invoiced", "paid") else None)
            self.assertIsNone(bd.deliverable_state(e, TODAY), status)

    def test_agreed_without_due_date_is_quiet(self):
        self.assertIsNone(bd.deliverable_state(
            entry(status="agreed", due=None), TODAY))


class TestInvoiceAging(unittest.TestCase):
    def test_boundaries_exact(self):
        cases = [
            ("2026-11-04", None),              # 0 days
            ("2026-10-22", None),              # 13: still current
            ("2026-10-21", ("chase", 14)),     # exact 14
            ("2026-10-06", ("chase", 29)),
            ("2026-10-05", ("overdue", 30)),   # exact 30
            ("2026-08-06", ("overdue", 90)),
        ]
        for invoiced, expected in cases:
            e = entry(status="invoiced", invoiced=invoiced)
            self.assertEqual(bd.invoice_state(e, TODAY), expected,
                             invoiced)

    def test_paid_deals_do_not_age(self):
        e = entry(status="paid", invoiced="2026-08-06")
        self.assertIsNone(bd.invoice_state(e, TODAY))
        self.assertIsNone(bd.invoice_age_days(e, TODAY))


class TestTransitions(unittest.TestCase):
    def test_pipeline_flow(self):
        flow = [("pitched", "negotiating"), ("pitched", "agreed"),
                ("negotiating", "pitched"),
                ("negotiating", "agreed"), ("agreed", "delivered"),
                ("delivered", "invoiced"), ("invoiced", "paid")]
        for old, new in flow:
            self.assertIn(new, bd.TRANSITIONS[old], (old, new))

    def test_any_live_stage_can_die(self):
        for old in ("pitched", "negotiating", "agreed", "delivered",
                    "invoiced"):
            self.assertIn("dead", bd.TRANSITIONS[old], old)

    def test_terminal_states_have_no_exits(self):
        self.assertEqual(bd.TRANSITIONS["paid"], ())
        self.assertEqual(bd.TRANSITIONS["dead"], ())


class TestMoveCli(BoardCase):
    def test_full_walk_stamps_invoice_date(self):
        self.write_board([entry(status="pitched")])
        for target in ("agreed", "delivered"):
            r = self.cli("move", "1", target, "--today", TODAY_S)
            self.assertEqual(r.returncode, 0, r.stdout)
        r = self.cli("move", "1", "invoiced", "--today", TODAY_S)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("Invoice date recorded as 2026-11-04", r.stdout)
        saved = json.loads(self.board.read_text())["deals"][0]
        self.assertEqual(saved["invoiced"], "2026-11-04")
        self.assertEqual(saved["status"], "invoiced")
        r = self.cli("move", "1", "paid", "--today", "2026-11-20")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("moved invoiced → paid", r.stdout)

    def test_move_out_of_paid_is_clean_error(self):
        self.write_board([entry(status="paid",
                                invoiced="2026-10-01")])
        before = self.board.read_bytes()
        r = self.cli("move", "1", "dead")
        self.assertEqual(r.returncode, 2)
        self.assertIn("terminal", r.stdout)
        self.assertEqual(self.board.read_bytes(), before)

    def test_move_out_of_dead_is_clean_error(self):
        self.write_board([entry(status="dead")])
        r = self.cli("move", "1", "pitched")
        self.assertEqual(r.returncode, 2)
        self.assertIn("terminal", r.stdout)

    def test_skipping_stages_is_clean_error(self):
        self.write_board([entry(status="agreed", due="2026-11-09")])
        r = self.cli("move", "1", "paid")
        self.assertEqual(r.returncode, 2)
        self.assertIn("cannot move from agreed to paid", r.stdout)
        self.assertIn("delivered", r.stdout)  # names the allowed moves

    def test_move_to_same_status_is_clean_error(self):
        self.write_board([entry(status="negotiating")])
        r = self.cli("move", "1", "negotiating")
        self.assertEqual(r.returncode, 2)
        self.assertIn("already negotiating", r.stdout)

    def test_missing_id_is_clean_error(self):
        self.write_board([entry()])
        r = self.cli("move", "99", "agreed")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no deal with id 99", r.stdout)

    def test_bad_status_is_argparse_error_json_in_json_mode(self):
        self.write_board([entry()])
        r = self.cli("move", "1", "shipped", "--json")
        self.assertEqual(r.returncode, 2)
        self.assertIn("error", json.loads(r.stdout))


class TestTotals(unittest.TestCase):
    def test_hand_computed(self):
        entries = [
            entry(id=1, fee=750.0, status="pitched"),
            entry(id=2, fee=1500.0, status="agreed"),
            entry(id=3, fee=900.0, status="agreed"),
            entry(id=4, fee=2000.0, status="delivered"),
            entry(id=5, fee=1100.0, status="invoiced",
                  invoiced="2026-10-20"),
            entry(id=6, fee=650.0, status="paid",
                  invoiced="2026-09-15"),
            entry(id=7, fee=800.0, status="dead"),
        ]
        t = bd.compute_totals(entries)
        self.assertEqual(t["by_status"]["agreed"],
                         {"count": 2, "amount": 2400.0})
        self.assertEqual(t["by_status"]["pitched"],
                         {"count": 1, "amount": 750.0})
        # delivered 2,000 + invoiced 1,100
        self.assertEqual(t["delivered_unpaid"], 3100.0)
        self.assertEqual(t["paid"], 650.0)


class TestSampleBoard(BoardCase):
    SAMPLE = EXAMPLES / "sample-board.json"

    def test_sample_due_sections_and_totals(self):
        r = run_cli("due", "--board", str(self.SAMPLE),
                    "--today", TODAY_S)
        self.assertEqual(r.returncode, 1)
        self.assertIn("DELIVERABLES DUE — agreed deals overdue or "
                      "due within 7 days (2):", r.stdout)
        self.assertIn("DELIVERED — INVOICE NOT SENT YET (1):",
                      r.stdout)
        self.assertIn("INVOICES OVERDUE — unpaid for 30+ days (1):",
                      r.stdout)
        self.assertIn("INVOICES TO CHASE — unpaid for 14+ days (1):",
                      r.stdout)
        # hand totals
        self.assertIn("agreed $2,400.00 (2)", r.stdout)
        self.assertIn("invoiced $2,850.00 (2)", r.stdout)
        self.assertIn("Delivered but unpaid: $4,850.00", r.stdout)
        self.assertIn("Paid: $650.00", r.stdout)
        self.assertIn("Action items: 5", r.stdout)

    def test_sample_ages_land_right(self):
        r = run_cli("due", "--board", str(self.SAMPLE), "--today",
                    TODAY_S, "--json")
        data = json.loads(r.stdout)
        dels = {e["id"]: e for e in data["deliverables"]}
        # id 4: due 2026-10-30 -> 5 days overdue; id 3: due in 5
        self.assertEqual((dels[4]["state"], dels[4]["days"]),
                         ("overdue", 5))
        self.assertEqual((dels[3]["state"], dels[3]["days"]),
                         ("due_soon", 5))
        chase = {e["id"]: e for e in data["invoices_chase"]}
        over = {e["id"]: e for e in data["invoices_overdue"]}
        # id 6: invoiced 2026-10-20 -> 15 days; id 7: 2026-09-28 -> 37
        self.assertEqual(chase[6]["invoice_age_days"], 15)
        self.assertEqual(over[7]["invoice_age_days"], 37)
        self.assertEqual([e["id"] for e in
                          data["delivered_uninvoiced"]], [5])
        # negotiating deal with a due date is NOT a deliverable item
        self.assertNotIn(2, dels)
        # paid and dead deals appear nowhere in the work view
        self.assertEqual(data["totals"]["paid"], 650.0)
        self.assertEqual(data["totals"]["delivered_unpaid"], 4850.0)

    def test_sample_has_every_status(self):
        r = run_cli("list", "--board", str(self.SAMPLE), "--today",
                    TODAY_S, "--json")
        statuses = {e["status"] for e in json.loads(r.stdout)["deals"]}
        self.assertEqual(statuses, set(bd.STATUSES))


class TestDueCli(BoardCase):
    def test_quiet_board_exits_0(self):
        self.write_board([
            entry(id=1, status="agreed", due="2026-11-12"),  # 8 days
            entry(id=2, status="invoiced", invoiced="2026-10-22",
                  fee=300.0),  # 13 days: current
            entry(id=3, status="paid", invoiced="2026-08-01",
                  fee=500.0),
        ])
        r = self.cli("due", "--today", TODAY_S)
        self.assertEqual(r.returncode, 0)
        self.assertIn("Nothing due", r.stdout)

    def test_empty_board_exits_0(self):
        self.write_board([])
        r = self.cli("due", "--today", TODAY_S)
        self.assertEqual(r.returncode, 0)
        self.assertIn("Nothing due", r.stdout)

    def test_deliverable_on_day_7_exits_1_day_8_exits_0(self):
        self.write_board([entry(status="agreed", due="2026-11-11")])
        self.assertEqual(self.cli("due", "--today", TODAY_S)
                         .returncode, 1)
        self.write_board([entry(status="agreed", due="2026-11-12")])
        self.assertEqual(self.cli("due", "--today", TODAY_S)
                         .returncode, 0)

    def test_delivered_uninvoiced_is_an_action_item(self):
        self.write_board([entry(status="delivered", fee=2000.0)])
        r = self.cli("due", "--today", TODAY_S)
        self.assertEqual(r.returncode, 1)
        self.assertIn("DELIVERED — INVOICE NOT SENT YET (1):",
                      r.stdout)
        self.assertIn("Send the invoice", r.stdout)

    def test_json_text_agreement(self):
        self.write_board([
            entry(id=1, status="agreed", due="2026-11-09",
                  fee=1500.0),
            entry(id=2, status="invoiced", invoiced="2026-10-05",
                  fee=1750.0),
            entry(id=3, status="delivered", fee=2000.0),
        ])
        text = self.cli("due", "--today", TODAY_S)
        js = self.cli("due", "--today", TODAY_S, "--json")
        self.assertEqual(text.returncode, 1)
        self.assertEqual(text.returncode, js.returncode)
        data = json.loads(js.stdout)
        self.assertEqual(data["action_items"], 3)
        # delivered 2,000 + invoiced 1,750
        self.assertEqual(data["totals"]["delivered_unpaid"], 3750.0)
        self.assertIn("$3,750.00", text.stdout)
        msg = data["invoices_overdue"][0]["message"]
        self.assertIn(msg, text.stdout)
        self.assertEqual(msg, bd.invoice_message(
            entry(status="invoiced", invoiced="2026-10-05",
                  fee=1750.0), TODAY))

    def test_cad_to_inr(self):
        self.write_board([entry(fee=1000.0)])
        r = self.cli("list", "--today", TODAY_S, "--cad-to-inr",
                     "67.97", "--json")
        data = json.loads(r.stdout)
        # 1000 * 67.97 = 67,970
        self.assertEqual(data["totals"]["by_status"]["pitched"]
                         ["amount_inr"], 67970.0)
        self.assertEqual(data["deals"][0]["fee_inr"], 67970.0)
        r2 = self.cli("list", "--today", TODAY_S, "--cad-to-inr",
                      "67.97")
        self.assertIn("₹67,970", r2.stdout)
        # entry lines carry the equivalent too (message lines never
        # do — they are copy-ready text, same rule as quote-follow-up)
        self.assertIn("$1,000.00 (₹67,970)", r2.stdout)

    def test_bad_cad_to_inr(self):
        self.write_board([entry()])
        r = self.cli("list", "--cad-to-inr", "-5")
        self.assertEqual(r.returncode, 2)
        self.assertIn("ERROR", r.stdout)


class TestMessages(unittest.TestCase):
    def test_deliverable_message_facts(self):
        e = entry(brand="Brightpath Tutoring", contact="Priya Nair",
                  deliverable="Sponsored tutorial video", fee=1500.0,
                  status="agreed", due="2026-11-09")
        msg = bd.deliverable_message(e, TODAY)
        for fact in ("Priya Nair", "Brightpath Tutoring",
                     "Sponsored tutorial video", "$1,500.00",
                     "2026-11-09", "5 days from now"):
            self.assertIn(fact, msg)

    def test_overdue_deliverable_message_facts(self):
        e = entry(brand="Kelowna Dental Studio",
                  contact="Dr. Sam Whitaker",
                  deliverable="Clinic tour reel", fee=900.0,
                  status="agreed", due="2026-10-30")
        msg = bd.deliverable_message(e, TODAY)
        self.assertIn("due on 2026-10-30, 5 days ago", msg)
        self.assertIn("$900.00", msg)

    def test_invoice_messages_facts(self):
        e = entry(brand="Summit Outdoor Co", contact="Casey Lin",
                  deliverable="Winter gear roundup", fee=1750.0,
                  status="invoiced", invoiced="2026-09-28")
        msg = bd.invoice_message(e, TODAY)
        for fact in ("Casey Lin", "Summit Outdoor Co",
                     "Winter gear roundup", "$1,750.00",
                     "2026-09-28", "37 days ago"):
            self.assertIn(fact, msg)
        e2 = entry(brand="Pinecrest Supplements",
                   contact="Taylor Brooks",
                   deliverable="Product review video", fee=1100.0,
                   status="invoiced", invoiced="2026-10-20")
        msg2 = bd.invoice_message(e2, TODAY)
        self.assertIn("15 days ago", msg2)
        self.assertIn("payment queue", msg2)

    def test_no_placeholders_no_invented_terms(self):
        samples = [
            entry(status="agreed", due="2026-11-09"),
            entry(status="agreed", due="2026-10-30"),
            entry(status="invoiced", invoiced="2026-10-20"),
            entry(status="invoiced", invoiced="2026-09-28"),
        ]
        msgs = [bd.deliverable_message(samples[0], TODAY),
                bd.deliverable_message(samples[1], TODAY),
                bd.invoice_message(samples[2], TODAY),
                bd.invoice_message(samples[3], TODAY),
                bd.delivered_next_step(entry(status="delivered"))]
        for msg in msgs:
            for bad in ("{", "}", "TODO", "XXX", "Lorem",
                        "net-30", "Net-30", "late fee", "final notice",
                        "act now", "Act now", "limited time",
                        "last chance", "urgent", "Urgent"):
                self.assertNotIn(bad, msg)

    def test_blank_contact_still_reads_cleanly(self):
        e = entry(contact="", status="invoiced",
                  invoiced="2026-10-20")
        msg = bd.invoice_message(e, TODAY)
        self.assertTrue(msg.startswith("Hi there,"))
        self.assertIn("Test Brand", msg)


class TestMutations(BoardCase):
    def test_add_creates_board_and_increments_ids(self):
        r = run_cli("add", "--board", str(self.board),
                    "--brand", "A Co", "--deliverable", "Reel",
                    "--fee", "100", "--due", "2026-11-09")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(self.board.is_file())
        r = run_cli("add", "--board", str(self.board),
                    "--brand", "B Co", "--contact", "Sam",
                    "--deliverable", "Short", "--fee", "250.50",
                    "--status", "agreed")
        self.assertEqual(r.returncode, 0, r.stdout)
        data = json.loads(self.board.read_text())
        self.assertEqual([d["id"] for d in data["deals"]], [1, 2])
        self.assertEqual(data["deals"][1]["fee"], 250.50)
        self.assertEqual(data["deals"][0]["status"], "pitched")
        self.assertEqual(data["deals"][0]["due"], "2026-11-09")
        self.assertIsNone(data["deals"][0]["invoiced"])

    def test_add_invoiced_status_stamps_invoice_date(self):
        r = run_cli("add", "--board", str(self.board),
                    "--brand", "A Co", "--deliverable", "Reel",
                    "--fee", "100", "--status", "invoiced",
                    "--today", TODAY_S)
        self.assertEqual(r.returncode, 0, r.stdout)
        saved = json.loads(self.board.read_text())["deals"][0]
        self.assertEqual(saved["invoiced"], TODAY_S)


class TestCorruptBoard(BoardCase):
    def test_invalid_json_errors_and_file_untouched(self):
        self.board.write_text('{"deals": [broken', encoding="utf-8")
        before = self.board.read_bytes()
        r = self.cli("due")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not valid JSON", r.stdout)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
        self.assertEqual(self.board.read_bytes(), before)

    def test_add_never_wipes_a_corrupt_board(self):
        self.board.write_text("not json at all", encoding="utf-8")
        before = self.board.read_bytes()
        r = run_cli("add", "--board", str(self.board),
                    "--brand", "A", "--deliverable", "D", "--fee",
                    "10")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.board.read_bytes(), before)

    def test_wrong_shape_errors(self):
        self.board.write_text('{"items": []}', encoding="utf-8")
        r = self.cli("list")
        self.assertEqual(r.returncode, 2)
        self.assertIn('"deals" key', r.stdout)

    def test_bad_entry_names_its_position(self):
        self.write_board([entry(), entry(id=2, fee=-5.0)])
        r = self.cli("list")
        self.assertEqual(r.returncode, 2)
        self.assertIn("entry 2", r.stdout)
        self.assertIn("'fee'", r.stdout)

    def test_invoiced_status_without_invoice_date_rejected(self):
        self.write_board([entry(status="invoiced", invoiced=None)])
        r = self.cli("list")
        self.assertEqual(r.returncode, 2)
        self.assertIn("'invoiced' date", r.stdout)

    def test_duplicate_ids_rejected(self):
        self.write_board([entry(id=1), entry(id=1, brand="Other")])
        r = self.cli("list")
        self.assertEqual(r.returncode, 2)
        self.assertIn("duplicate id 1", r.stdout)

    def test_bad_status_and_bad_dates_rejected(self):
        self.write_board([entry(status="shipped")])
        self.assertEqual(self.cli("list").returncode, 2)
        self.write_board([entry(due="2026-13-40")])
        r = self.cli("list")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not a real calendar date", r.stdout)
        self.write_board([entry(due="Nov 9 2026")])
        self.assertEqual(self.cli("list").returncode, 2)

    def test_nan_fee_in_board_rejected(self):
        self.board.write_text(
            '{"deals": [{"id": 1, "brand": "A", "deliverable": "D",'
            ' "fee": NaN}]}', encoding="utf-8")
        r = self.cli("list")
        self.assertEqual(r.returncode, 2)


class TestCliValidation(BoardCase):
    def test_bad_today_flag(self):
        self.write_board([entry()])
        r = self.cli("due", "--today", "next friday")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--today", r.stdout)

    def test_add_rejects_nan_and_negative_fees(self):
        for bad in ("nan", "inf", "-1"):
            r = run_cli("add", "--board", str(self.board),
                        "--brand", "A", "--deliverable", "D",
                        "--fee", bad)
            self.assertEqual(r.returncode, 2, bad)
            self.assertFalse(self.board.exists())

    def test_add_rejects_blank_brand_and_deliverable(self):
        r = run_cli("add", "--board", str(self.board), "--brand",
                    "   ", "--deliverable", "D", "--fee", "10")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--brand", r.stdout)
        r = run_cli("add", "--board", str(self.board), "--brand",
                    "A", "--deliverable", "  ", "--fee", "10")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--deliverable", r.stdout)

    def test_add_rejects_bad_due_date(self):
        r = run_cli("add", "--board", str(self.board), "--brand",
                    "A", "--deliverable", "D", "--fee", "10",
                    "--due", "2026-02-30")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not a real calendar date", r.stdout)

    def test_argparse_error_is_json_in_json_mode(self):
        r = run_cli("add", "--board", str(self.board), "--fee",
                    "10", "--json")  # missing --brand/--deliverable
        self.assertEqual(r.returncode, 2)
        self.assertIn("error", json.loads(r.stdout))

    def test_error_is_json_object_in_json_mode(self):
        r = self.cli("due", "--json")
        self.assertEqual(r.returncode, 2)
        self.assertIn("board not found", json.loads(r.stdout)["error"])

    def test_missing_board_is_clean_error(self):
        r = self.cli("list")
        self.assertEqual(r.returncode, 2)
        self.assertIn("board not found", r.stdout)

    def test_no_command_is_clean_error(self):
        r = run_cli()
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
