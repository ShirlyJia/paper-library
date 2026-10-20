import copy
import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


queue = load("review_queue")
daily = load("collect_daily")
apply_review = load("apply_review")

REVIEW = {"reviewStatus": "completed", "claim": "c", "contribution": "c", "evidence": "e", "limitations": "l",
          "value": "v", "reproducibility": "r", "conclusion": "证据已支持", "sources": ["https://a"], "readScope": "方法与实验"}
PAPER = {"id": "arxiv-2610.00001", "title": "New", "date": "2026-10-10", "updated": "2026-10-10", "category": 1,
         "section": "s", "topicId": "t", "status": "preprint", "venue": "预印本", "summary": "s",
         "url": "https://arxiv.org/abs/2610.00001", "pdf": None, "code": None}


class QueueTests(unittest.TestCase):
    def test_independent_channels_and_title_hits_rank_first(self):
        pattern = queue.re.compile("tabular", queue.re.I)
        strong = {"title": "Tabular X", "abstract": "a", "discoveredVia": ["models", "openalex:semantic:a", "https://iclr.cc"]}
        weak = {"title": "X", "abstract": "tabular", "discoveredVia": ["models", "methods-and-causal"]}
        self.assertGreater(queue.score(strong, pattern), queue.score(weak, pattern))
        self.assertEqual(queue.score(weak, pattern), 1)

    def test_existing_papers_reopen_only_on_new_revision_or_venue(self):
        papers = {"p": {"updated": "2026-10-01", "status": "preprint"}}
        self.assertFalse(queue.needs_update_check({"existingIds": ["p"], "updated": "2026-10-01"}, papers))
        self.assertTrue(queue.needs_update_check({"existingIds": ["p"], "updated": "2026-10-05"}, papers))
        self.assertTrue(queue.needs_update_check({"existingIds": ["p"], "officialDecision": "Accept"}, papers))


class ApplyReviewTests(unittest.TestCase):
    def setUp(self):
        self.catalogue = {"categories": [{"id": 1, "name": "A"}],
                          "papers": [{**PAPER, "id": "old", "url": "https://x/old", "addedAt": "2026-10-01"}]}
        self.decisions, self.registry = [], {"families": []}

    def run_apply(self, bundle):
        return apply_review.apply(bundle, self.catalogue, self.decisions, self.registry)

    def test_inclusion_updates_catalogue_decisions_and_family(self):
        self.run_apply({"date": "2026-10-16", "included": [{"paper": PAPER, "qualityReview": REVIEW, "brief": "b", "family": "NewFM"}],
                        "deferred": [{"id": "d", "title": "D", "url": "https://d", "sourceUpdated": "2026-10-01", "reason": "需全文"}]})
        self.assertEqual([p["id"] for p in self.catalogue["papers"]], ["old", PAPER["id"]])
        self.assertEqual([d["decision"] for d in self.decisions], ["included", "deferred"])
        self.assertEqual(self.registry["families"][0]["paperIds"], [PAPER["id"]])
        digest = apply_review.direction_digest({"included": [{"paper": {**PAPER, "aliases": ["NewFM"]}, "qualityReview": REVIEW, "brief": "一句话"}]}, self.catalogue)
        self.assertIn("### 业界进展（1 篇）", digest)
        self.assertIn("**[NewFM](https://arxiv.org/abs/2610.00001)**：一句话", digest)

    def test_abstract_only_reviews_and_missing_reasons_are_rejected(self):
        for bundle in [{"date": "d", "included": [{"paper": PAPER, "qualityReview": {**REVIEW, "reviewStatus": "partial"}, "brief": "b"}]},
                       {"date": "d", "included": [{"paper": PAPER, "qualityReview": REVIEW}]},
                       {"date": "d", "included": [{"paper": PAPER, "qualityReview": {**REVIEW, "conclusion": "很好"}, "brief": "b"}]},
                       {"date": "d", "excluded": [{"id": "e", "title": "E", "url": "https://e", "reason": ""}]}]:
            with self.subTest(bundle=bundle), self.assertRaises(ValueError):
                self.run_apply(copy.deepcopy(bundle))

    def test_correction_keeps_original_collection_date(self):
        fixed = {**PAPER, "id": "old", "url": "https://x/old", "summary": "corrected"}
        self.run_apply({"date": "2026-10-16", "corrected": [{"paper": fixed, "qualityReview": REVIEW, "brief": "b"}]})
        self.assertEqual(self.catalogue["papers"][0]["addedAt"], "2026-10-01")
        self.assertEqual(self.decisions[0]["decision"], "existing")



class BriefingTests(unittest.TestCase):
    def test_briefing_holds_conclusions_and_run_notes_hold_process(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            (run / "briefing-highlights.md").write_text("## 今天的看点\n\n主线叙述")
            plan = {"until": "2026-10-16"}
            channels = {"arxiv": {"status": "complete"}, "formal": {"status": "not-due"},
                        "fulltext": {"status": "incomplete", "failures": [{"status": "truncated", "error": "needs key"}]}}
            applied = {"included": [{"paper": {**PAPER, "category": 1}, "qualityReview": REVIEW, "brief": "一句话"}],
                       "deferred": [{"title": "D", "url": "https://d", "reason": "需全文"}]}
            queue_state = {"items": [{"open": True, "score": 7}, {"open": True, "score": 1}]}
            text = daily.write_briefing(run, plan, applied).read_text()
            for expected in ["今天收录 1 篇（近一个月的新论文 1 篇）", "归入业界进展方向", "## 今天的看点", "### 业界进展（1 篇）", "：一句话"]:
                self.assertIn(expected, text)
            self.assertLess(text.index("今天的看点"), text.index("各方向上新"))
            for process in ["暂缓", "队列", "OpenAlex", "上线", "贡献：", REVIEW["limitations"] + " "]:
                self.assertNotIn(process, text)
            notes = daily.write_run_notes(run, plan, channels, applied, queue_state, False, ["note"]).read_text()
            for expected in ["OpenAlex 全文：1 项未完成（needs key）", "尚未上线", "- note", "[D](https://d)：需全文",
                             "待审队列：2 条，其中高相关 1 条"]:
                self.assertIn(expected, notes)
            self.assertIsNone(daily.write_briefing(run, plan, {"deferred": applied["deferred"]}))

if __name__ == "__main__":
    unittest.main()
