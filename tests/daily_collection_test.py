import importlib.util
import unittest
import json
import tempfile
from unittest.mock import patch
from types import SimpleNamespace
from datetime import date
from pathlib import Path

spec = importlib.util.spec_from_file_location("collect_daily", Path(__file__).resolve().parents[1] / "scripts/collect_daily.py")
daily = importlib.util.module_from_spec(spec)
spec.loader.exec_module(daily)


def groups(plan):
    return {name: group["since"] for group in plan["groups"] for name in group["channels"]}


class DailyWindowTests(unittest.TestCase):
    def test_automatic_sources_import_queue_once(self):
        calls = []
        def fake_run(command, **kwargs):
            calls.append(command)
            if command[1].endswith("collect.py"):
                Path(command[-1]).write_text(json.dumps({"runs": [], "candidates": []}))
            return SimpleNamespace(returncode=0)
        plan = {"until": "2026-10-29", "groups": [{"since": "2026-10-22", "channels": ["arxiv", "fulltext"]}]}
        with tempfile.TemporaryDirectory() as folder, patch.object(daily.subprocess, "run", side_effect=fake_run):
            self.assertEqual(daily.run_automatic(plan, Path(folder)), 0)
        imports = [c for c in calls if c[1].endswith("review_queue.py")]
        self.assertEqual(len(imports), 1)
        self.assertTrue(imports[0][-2].endswith("candidates-arxiv.json"))
        self.assertTrue(imports[0][-1].endswith("candidates-fulltext.json"))

    def test_first_run_backfills_six_months_and_clamps_month_end(self):
        plan = daily.plan_window(date(2026, 8, 31), {})
        self.assertEqual(set(groups(plan).values()), {"2026-02-28"})
        self.assertEqual(set(groups(plan)), set(daily.CHANNELS))

    def test_one_failed_channel_does_not_force_others_into_backfill(self):
        state = {"channels": {"arxiv": "2026-10-12", "formal": "2026-10-10", "semantic": "2026-10-10",
                              "citations": "2026-10-10", "references": "2026-10-10", "consensus": "2026-10-10",
                              "families": "2026-10-10"}}
        plan = daily.plan_window(date(2026, 10, 13), state)
        self.assertEqual(groups(plan), {"arxiv": "2026-10-06", "fulltext": "2026-04-13", "web": "2026-04-13"})
        self.assertEqual({s["channel"] for s in plan["skipped"]}, {"formal", "semantic", "citations", "consensus", "families", "references"})
        self.assertEqual([x["channel"] for x in plan["manual"]], ["web"])

    def test_manual_weekly_channels_are_listed_when_due(self):
        plan = daily.plan_window(date(2026, 10, 13), {})
        self.assertEqual([item["channel"] for item in plan["manual"]], ["web", "consensus", "families"])

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

    def test_daily_alternatives_and_weekly_backfill_are_independent(self):
        state = {"channels": {n: "2026-10-20" for n in daily.CHANNELS}, "backfills": {"fulltext": "2026-10-15"}}
        first = daily.plan_window(date(2026, 10, 21), state)
        self.assertEqual(set(groups(first)), {"arxiv", "fulltext"})
        self.assertEqual(groups(first)["fulltext"], "2026-10-14")
        state["channels"]["fulltext"] = "2026-10-21"
        second = daily.plan_window(date(2026, 10, 22), state)
        self.assertEqual(groups(second)["fulltext"], "2026-04-22")
        self.assertEqual(second["backfillChannels"], ["fulltext"])

    def test_quota_cooldown_preserves_gap_and_resumes_at_reset(self):
        state = {"channels": {"consensus": "2026-10-01"}, "cooldowns": {"consensus": {"retryAfter": "2026-11-01", "reason": "monthly quota"}}}
        plan = daily.plan_window(date(2026, 10, 21), state)
        self.assertNotIn("consensus", groups(plan))
        self.assertIn("web", groups(plan))
        self.assertEqual(state["channels"]["consensus"], "2026-10-01")
        self.assertIn("consensus", groups(daily.plan_window(date(2026, 11, 1), state)))

    def test_web_sweep_requires_evidence_for_all_lanes(self):
        lanes = json.loads(daily.WEB_CONFIG.read_text())["lanes"]
        report = {"runs": [{"source": l["id"], "channel": "web", "status": "complete", "query": "actual query", "evidence": ["https://example.org"], "note": "no relevant new result"} for l in lanes]}
        self.assertEqual(daily.web_report_errors(report), [])
        report["runs"][0]["evidence"] = []
        self.assertEqual(daily.web_report_errors(report), [lanes[0]["id"]])
        self.assertTrue(daily.web_report_errors({"runs": []}))

    def test_crashed_source_and_failed_queue_do_not_block_next_source(self):
        plan = {"until": "2026-10-21", "groups": [{"since": "2026-10-14", "channels": ["arxiv", "fulltext", "references"]}]}
        collected = []
        def fake_run(command, **kwargs):
            if command[1].endswith("collect.py"):
                name = command[command.index("--channels") + 1]
                collected.append(name)
                if name == "arxiv":
                    raise OSError("provider unavailable")
                Path(command[-1]).write_text(json.dumps({"runs": [], "candidates": []}))
                return SimpleNamespace(returncode=0)
            return SimpleNamespace(returncode=1 if any(str(c).endswith("fulltext.json") for c in command) else 0)
        with tempfile.TemporaryDirectory() as folder, patch.object(daily.subprocess, "run", side_effect=fake_run):
            result = daily.run_automatic(plan, Path(folder))
            self.assertNotEqual(result, 0)
            self.assertEqual(collected, ["arxiv", "fulltext", "references"])
            self.assertTrue((Path(folder) / "candidates-fulltext.json").exists())
            self.assertTrue((Path(folder) / "candidates-fulltext-error.json").exists())

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
