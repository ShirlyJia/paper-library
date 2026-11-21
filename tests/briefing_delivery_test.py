import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("send_briefing", Path(__file__).resolve().parents[1] / "scripts/send_briefing.py")
sender = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sender)


class BriefingDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = datetime(2026, 11, 20, 15, 59, 59, tzinfo=timezone.utc)
        clock = patch.object(sender, "datetime", wraps=datetime)
        clock.start().now.side_effect = lambda tz: self.now.astimezone(tz)
        self.addCleanup(clock.stop)
        self.root = Path(self.temp.name)
        self.run = self.root / "work/collection/daily/2026-10-19/run"
        self.run.mkdir(parents=True)
        self.config_path = self.root / "work/notifications/feishu.json"
        self.config = {"enabled": True, "identity": "user", "chatName": "研究群", "chatId": "oc_test", "notBefore": "2026-10-19"}
        sender.save_json(self.config_path, self.config)
        self.paper = {"id": "paper-1", "title": "Paper One", "url": "https://arxiv.org/abs/2610.12345"}
        sender.save_json(self.root / "data/papers.json", {"papers": [self.paper]})
        self.review = {"date": "2026-10-19", "decisions": {"included": ["paper-1"], "corrected": []},
                       "publication": {"published": True}, "briefing": str((self.run / "briefing.md").relative_to(self.root))}
        sender.save_json(self.run / "review.json", self.review)
        (self.run / "briefing.md").write_text("# 结构化数据研究小报｜2026-10-19\n\n新增 1 篇。\n\n[Paper One](https://arxiv.org/abs/2610.12345)\n")
        self.calls = []
        self.mode = "normal"
        self.body = sender.prepare(self.run, self.root)["body"]

    def fake_cli(self, args, identity):
        self.calls.append(args)
        if args[:3] == ["im", "chats", "get"]:
            return {"name": "研究群", "chat_mode": "topic", "chat_status": "normal"}
        if args[1] == "+messages-send":
            if self.mode == "timeout":
                raise sender.DeliveryError("timeout", uncertain=True)
            if self.mode == "rejected":
                raise sender.DeliveryError("rejected")
            return {"message_id": "om_sent"}
        if args[1] in {"+messages-mget", "+chat-messages-list"}:
            if self.mode == "read-fails":
                raise sender.DeliveryError("read temporarily unavailable")
            if self.mode == "not-found":
                return {"messages": [], "has_more": False}
            return {"messages": [{"message_id": "om_sent", "content": self.body, "deleted": False}], "has_more": False}
        raise AssertionError(args)

    def deliver(self, **kwargs):
        with patch.object(sender, "cli", side_effect=self.fake_cli), patch.object(sender, "verify_live"):
            return sender.deliver(self.run, self.config, self.config_path, self.root, **kwargs)

    def sends(self):
        return sum(args[1] == "+messages-send" for args in self.calls)

    def receipt(self):
        return next((self.root / "work/notifications/receipts").glob("*.json"))

    def test_unpublished_and_no_change_runs_do_not_send(self):
        self.review["publication"]["published"] = False
        sender.save_json(self.run / "review.json", self.review)
        with self.assertRaisesRegex(ValueError, "上线"):
            self.deliver()
        self.review["decisions"]["included"] = []
        sender.save_json(self.run / "review.json", self.review)
        self.assertEqual(self.deliver()["status"], "no-changes")
        self.assertEqual(self.calls, [])

    def test_preview_never_accesses_feishu(self):
        self.assertEqual(self.deliver(dry_run=True)["status"], "preview")
        self.assertEqual(self.calls, [])

    def test_weekend_blocks_automatic_and_manual_delivery_in_beijing(self):
        start_of_saturday = self.now + timedelta(seconds=1)
        with patch.object(sender, "cli") as cli:
            for now in (start_of_saturday, start_of_saturday + timedelta(days=1)):
                self.now = now
                for run in (None, self.run):
                    results = sender.send_pending(self.config_path, self.root, run_dir=run)
                    self.assertEqual(results, [{"status": "weekend-skipped"}])
            self.assertFalse(self.config_path.with_name("delivery.lock").exists())
            self.assertFalse(self.config_path.with_name("receipts").exists())
            results = sender.send_pending(self.config_path, self.root, run_dir=self.run, dry_run=True)
            self.assertEqual(results[0]["status"], "preview")
            cli.assert_not_called()
        self.now = start_of_saturday + timedelta(days=2)
        self.assertEqual(self.deliver()["status"], "sent-and-verified")

    def test_crossing_midnight_during_live_check_defers_delivery(self):
        def verify_live(prepared):
            self.now += timedelta(seconds=1)

        with patch.object(sender, "cli", side_effect=self.fake_cli):
            with patch.object(sender, "verify_live", side_effect=verify_live):
                results = sender.send_pending(self.config_path, self.root)
        self.assertEqual(results, [{"status": "weekend-skipped"}])
        self.assertEqual(self.sends(), 0)
        self.assertFalse(self.config_path.with_name("receipts").exists())

    def test_crossing_midnight_at_send_boundary_preserves_the_existing_receipt(self):
        self.mode = "rejected"
        with self.assertRaises(sender.DeliveryError):
            self.deliver()
        self.mode = "normal"
        receipt = self.receipt()
        before = receipt.read_bytes()
        save_json = sender.save_json

        def save_and_advance(path, data):
            save_json(path, data)
            if path == receipt and data["status"] == "sending":
                self.now += timedelta(seconds=1)

        with patch.object(sender, "save_json", side_effect=save_and_advance):
            self.assertEqual(self.deliver()["status"], "weekend-skipped")
        self.assertEqual(receipt.read_bytes(), before)
        self.assertEqual(self.sends(), 1)

    def test_existing_site_footer_is_preserved_without_duplicate(self):
        path = self.run / "briefing.md"
        original = path.read_text()
        for footer in [f"访问站点：{sender.SITE}", f"访问站点：[{sender.SITE}]({sender.SITE})"]:
            path.write_text(original + "\n" + footer + "\n")
            body = sender.prepare(self.run, self.root)["body"]
            self.assertEqual(body.count("访问站点："), 1)
            self.assertTrue(body.endswith(footer))

    def test_send_readback_and_deduplicate_across_runs(self):
        self.assertEqual(self.deliver()["status"], "sent-and-verified")
        self.config.update(identity="bot", cliConfigDir="paper-bot-cli", botOpenId="ou_new")
        self.assertEqual(self.deliver()["status"], "already-sent")
        self.assertEqual(self.sends(), 1)
        self.assertTrue((self.run / "feishu-delivery.json").exists())
        other = self.run.parent / "retry"
        other.mkdir()
        (other / "briefing.md").write_text((self.run / "briefing.md").read_text())
        sender.save_json(other / "review.json", {**self.review, "briefing": str((other / "briefing.md").relative_to(self.root))})
        with patch.object(sender, "cli", side_effect=self.fake_cli):
            self.assertEqual(sender.deliver(other, self.config, self.config_path, self.root)["status"], "already-sent")
        self.assertEqual(self.sends(), 1)

    def test_project_bot_profile_is_used_for_sending_and_recovery(self):
        self.config.update(identity="bot", cliConfigDir="paper-bot-cli", botOpenId="ou_new")
        profile = (self.config_path.parent / "paper-bot-cli").resolve()
        active_bot = "ou_default"

        def project_cli(args, identity, *, config_dir):
            self.assertEqual(identity, "bot")
            self.assertEqual(config_dir, profile)
            if args == ["api", "GET", "/open-apis/bot/v3/info"]:
                return {"bot": {"open_id": active_bot, "activate_status": 2}}
            return self.fake_cli(args, identity)

        def deliver():
            return sender.deliver(self.run, self.config, self.config_path, self.root)

        with patch.object(sender, "cli", side_effect=project_cli), patch.object(sender, "verify_live"):
            with self.assertRaisesRegex(ValueError, "机器人.*不符"):
                deliver()
            self.assertEqual(self.sends(), 0)
            active_bot = "ou_new"
            self.mode = "timeout"
            with self.assertRaises(sender.DeliveryError):
                deliver()
            self.mode = "normal"
            self.assertEqual(deliver()["status"], "sent-and-verified")
        self.assertEqual(self.sends(), 1)

    def test_timeout_recovers_from_group_history_without_resending(self):
        self.mode = "timeout"
        with self.assertRaises(sender.DeliveryError):
            self.deliver()
        self.mode = "normal"
        self.assertEqual(self.deliver()["status"], "sent-and-verified")
        self.assertEqual(self.sends(), 1)

    def test_unknown_old_result_blocks_blind_retry(self):
        self.mode = "timeout"
        with self.assertRaises(sender.DeliveryError):
            self.deliver()
        receipt = sender.read_json(self.receipt())
        receipt["attemptedAt"] = (self.now - timedelta(hours=2)).isoformat()
        sender.save_json(self.receipt(), receipt)
        self.mode = "not-found"
        with self.assertRaisesRegex(sender.DeliveryError, "安全重试窗口"):
            self.deliver()
        self.assertEqual(self.sends(), 1)

    def test_readback_failure_only_retries_reading(self):
        self.mode = "read-fails"
        with self.assertRaises(sender.DeliveryError):
            self.deliver()
        self.mode = "normal"
        self.deliver()
        self.assertEqual(self.sends(), 1)

    def test_changed_body_does_not_create_duplicate_topic(self):
        self.deliver()
        path = self.run / "briefing.md"
        path.write_text(path.read_text() + "\n修改后的说明。\n")
        with self.assertRaisesRegex(ValueError, "正文已变化"):
            self.deliver()
        self.assertEqual(self.sends(), 1)

    def archive_paper(self):
        sender.save_json(self.root / "research/withheld-papers.json", {"papers": [{"paper": self.paper}]})
        sender.save_json(self.root / "data/papers.json", {"papers": []})

    def test_verified_briefing_still_deduplicates_after_paper_withdrawal(self):
        self.deliver()
        self.archive_paper()
        calls = len(self.calls)
        self.assertEqual(self.deliver()["status"], "already-sent")
        self.assertEqual(len(self.calls), calls)
        self.assertEqual(self.sends(), 1)

    def test_unsent_briefing_with_withdrawn_paper_is_not_delivered(self):
        self.archive_paper()
        with self.assertRaisesRegex(ValueError, "已撤下"):
            self.deliver()
        self.assertEqual(self.sends(), 0)

    def test_changed_paper_list_does_not_create_duplicate_topic(self):
        self.deliver()
        second = {"id": "paper-2", "title": "Paper Two", "url": "https://arxiv.org/abs/2610.54321"}
        sender.save_json(self.root / "data/papers.json", {"papers": [self.paper, second]})
        self.review["decisions"]["included"].append(second["id"])
        sender.save_json(self.run / "review.json", self.review)
        path = self.run / "briefing.md"
        path.write_text(path.read_text() + f"\n[Paper Two]({second['url']})\n")
        with self.assertRaisesRegex(ValueError, "论文清单已变化"):
            self.deliver()
        self.assertEqual(self.sends(), 1)

    def test_missing_paper_link_or_private_paths_block_delivery(self):
        path = self.run / "briefing.md"
        original = path.read_text()
        for text in [original.replace(self.paper["url"], "https://example.com"), original + "\nwork/collection/private.md"]:
            path.write_text(text)
            with self.assertRaises(ValueError):
                self.deliver()
        self.assertEqual(self.sends(), 0)

    def test_group_mismatch_blocks_delivery(self):
        with patch.object(sender, "cli", return_value={"name": "another", "chat_mode": "topic", "chat_status": "normal"}):
            with self.assertRaisesRegex(ValueError, "授权目标"):
                sender.deliver(self.run, self.config, self.config_path, self.root)

    def test_live_mismatch_blocks_delivery(self):
        with patch.object(sender, "cli", side_effect=self.fake_cli), patch.object(sender, "verify_live", side_effect=ValueError("线上数据不一致")):
            with self.assertRaisesRegex(ValueError, "线上数据"):
                sender.deliver(self.run, self.config, self.config_path, self.root)
        self.assertEqual(self.sends(), 0)

    def test_activation_date_does_not_backfill_older_briefings(self):
        sender.save_json(self.config_path, {**self.config, "notBefore": "2026-10-20"})
        with patch.object(sender, "cli", side_effect=self.fake_cli):
            self.assertEqual(sender.send_pending(self.config_path, self.root), [])
        self.assertEqual(self.calls, [])

    def test_failed_backfill_allows_later_delivery_and_keeps_deduplication(self):
        self.mode = "timeout"
        with self.assertRaises(sender.DeliveryError):
            self.deliver()
        earlier_receipt = self.receipt()
        data = sender.read_json(earlier_receipt)
        data["attemptedAt"] = (self.now - timedelta(hours=2)).isoformat()
        sender.save_json(earlier_receipt, data)
        prior = earlier_receipt.read_bytes()

        date = "2026-10-20"
        later = self.run.parent.parent / date / "run"
        later.mkdir(parents=True)
        briefing = later / "briefing.md"
        briefing.write_text((self.run / "briefing.md").read_text().replace(self.review["date"], date))
        sender.save_json(later / "review.json", {**self.review, "date": date,
                                                 "briefing": str(briefing.relative_to(self.root))})
        self.body = sender.prepare(later, self.root)["body"]
        self.mode = "normal"

        def unavailable_history(args, identity):
            if args[1] == "+chat-messages-list":
                return {"messages": [], "has_more": False}
            return self.fake_cli(args, identity)

        with patch.object(sender, "cli", side_effect=unavailable_history), patch.object(sender, "verify_live"):
            first = sender.send_pending(self.config_path, self.root)
            second = sender.send_pending(self.config_path, self.root)
        self.assertEqual([item["status"] for item in first], ["failed", "sent-and-verified"])
        self.assertEqual([item["status"] for item in second], ["failed", "already-sent"])
        self.assertIn("安全重试窗口", first[0]["error"])
        self.assertEqual(earlier_receipt.read_bytes(), prior)
        self.assertEqual(self.sends(), 2)


if __name__ == "__main__":
    unittest.main()
