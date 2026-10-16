import importlib.util
import unittest
from datetime import date
from pathlib import Path

spec = importlib.util.spec_from_file_location("collect_daily", Path(__file__).resolve().parents[1] / "scripts/collect_daily.py")
daily = importlib.util.module_from_spec(spec)
spec.loader.exec_module(daily)


def groups(plan):
    return {name: group["since"] for group in plan["groups"] for name in group["channels"]}


class DailyWindowTests(unittest.TestCase):
    def test_first_run_backfills_six_months_and_clamps_month_end(self):
        plan = daily.plan_window(date(2026, 8, 31), {})
        self.assertEqual(set(groups(plan).values()), {"2026-02-28"})
        self.assertEqual(set(groups(plan)), set(daily.CHANNELS))

    def test_one_failed_channel_does_not_force_others_into_backfill(self):
        state = {"channels": {"arxiv": "2026-10-12", "formal": "2026-10-10", "semantic": "2026-10-10",
                              "citations": "2026-10-10", "references": "2026-10-10", "consensus": "2026-10-10",
                              "families": "2026-10-10"}}
        plan = daily.plan_window(date(2026, 10, 13), state)
        self.assertEqual(groups(plan), {"arxiv": "2026-10-06", "fulltext": "2026-04-13"})
        self.assertEqual({s["channel"] for s in plan["skipped"]}, {"formal", "semantic", "citations", "references", "consensus", "families"})
        self.assertEqual(plan["manual"], [])

    def test_manual_weekly_channels_are_listed_when_due(self):
        plan = daily.plan_window(date(2026, 10, 13), {})
        self.assertEqual([item["channel"] for item in plan["manual"]], ["consensus", "families"])

    def test_weekly_channels_come_due_after_seven_days(self):
        state = {"channels": {name: "2026-10-06" for name in daily.CHANNELS}}
        self.assertEqual(groups(daily.plan_window(date(2026, 10, 13), state))["formal"], "2026-04-13")

    def test_interruption_does_not_leave_a_gap(self):
        state = {"channels": {name: "2026-01-15" for name in daily.CHANNELS}}
        self.assertEqual(set(groups(daily.plan_window(date(2026, 10, 13), state)).values()), {"2026-01-12"})

    def test_invalid_checkpoints_do_not_silently_skip_dates(self):
        for state in [{"channels": {"arxiv": "2026-10-14"}}, {"channels": {"arxiv": "invalid"}}, {"channels": {"rss": "2026-10-01"}}]:
            with self.subTest(state=state), self.assertRaises(ValueError):
                daily.plan_window(date(2026, 10, 13), state)

    def test_only_fully_completed_channels_count_as_complete(self):
        plan = {"groups": [{"since": "2026-10-06", "channels": ["arxiv", "fulltext", "semantic"]}], "skipped": []}
        reports = [{"runs": [{"source": "a", "channel": "arxiv", "status": "complete"},
                             {"source": "f", "channel": "fulltext", "status": "truncated", "error": "needs key"}]}]
        status = daily.channel_status(plan, reports)
        self.assertEqual({k: v["status"] for k, v in status.items()},
                         {"arxiv": "complete", "fulltext": "incomplete", "semantic": "incomplete"})

    def test_review_schema_rejects_drift_and_false_checkpoints(self):
        review = {key: None for key in daily.REVIEW_KEYS}
        review.update(schemaVersion=2, channels={"arxiv": {"status": "incomplete"}}, qualityReviewedIds=[],
                      decisions={"included": [], "corrected": [], "deferred": [], "excluded": []},
                      checkpoint={"advanced": [], "kept": ["arxiv"]})
        daily.validate_review(review)
        with self.assertRaises(ValueError):
            daily.validate_review({**review, "checkpoint": {"advanced": ["arxiv"], "kept": []}})
        with self.assertRaises(ValueError):
            daily.validate_review({**review, "checkpointAdvanced": True})
        with self.assertRaises(ValueError):
            daily.validate_review({**review, "qualityReviewedIds": ["arxiv-1"]})


if __name__ == "__main__":
    unittest.main()
