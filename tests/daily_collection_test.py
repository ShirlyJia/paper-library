import importlib.util
import unittest
from datetime import date
from pathlib import Path

spec = importlib.util.spec_from_file_location("collect_daily", Path(__file__).resolve().parents[1] / "scripts/collect_daily.py")
daily = importlib.util.module_from_spec(spec)
spec.loader.exec_module(daily)


class DailyWindowTests(unittest.TestCase):
    def test_first_run_backfills_six_months_and_clamps_month_end(self):
        plan = daily.plan_window(date(2026, 8, 31), {})
        self.assertEqual((plan["mode"], plan["since"], plan["until"]), ("backfill", "2026-02-28", "2026-08-31"))

    def test_daily_window_overlaps_seven_days(self):
        state = {"lastCompleted": "2026-10-12", "lastBackfill": "2026-10-10"}
        plan = daily.plan_window(date(2026, 10, 13), state)
        self.assertEqual((plan["mode"], plan["since"]), ("incremental", "2026-10-06"))
        self.assertEqual(state["lastCompleted"], "2026-10-12")

    def test_backfill_is_due_after_seven_days(self):
        plan = daily.plan_window(date(2026, 10, 13), {"lastCompleted": "2026-10-12", "lastBackfill": "2026-10-06"})
        self.assertEqual((plan["mode"], plan["since"]), ("backfill", "2026-04-13"))

    def test_interruption_does_not_leave_a_gap(self):
        plan = daily.plan_window(date(2026, 10, 13), {"lastCompleted": "2026-01-15", "lastBackfill": "2026-01-15"})
        self.assertEqual(plan["since"], "2026-01-12")

    def test_invalid_checkpoints_do_not_silently_skip_dates(self):
        for state in [
            {"lastCompleted": "2026-10-14"},
            {"lastCompleted": "2026-10-10", "lastBackfill": "2026-10-12"},
            {"lastBackfill": "2026-10-12"},
            {"lastCompleted": "invalid"},
        ]:
            with self.subTest(state=state), self.assertRaises(ValueError):
                daily.plan_window(date(2026, 10, 13), state)


if __name__ == "__main__":
    unittest.main()
