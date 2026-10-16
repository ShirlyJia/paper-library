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
        self.run_apply({"date": "2026-10-16", "included": [{"paper": PAPER, "qualityReview": REVIEW, "family": "NewFM"}],
                        "deferred": [{"id": "d", "title": "D", "url": "https://d", "sourceUpdated": "2026-10-01", "reason": "需全文"}]})
        self.assertEqual([p["id"] for p in self.catalogue["papers"]], ["old", PAPER["id"]])
        self.assertEqual([d["decision"] for d in self.decisions], ["included", "deferred"])
        self.assertEqual(self.registry["families"][0]["paperIds"], [PAPER["id"]])
        self.assertIn("审核依据：e", apply_review.briefing_list({"included": [{"paper": PAPER, "qualityReview": REVIEW}]}, self.catalogue))

    def test_abstract_only_reviews_and_missing_reasons_are_rejected(self):
        for bundle in [{"date": "d", "included": [{"paper": PAPER, "qualityReview": {**REVIEW, "reviewStatus": "partial"}}]},
                       {"date": "d", "included": [{"paper": PAPER, "qualityReview": {**REVIEW, "conclusion": "很好"}}]},
                       {"date": "d", "excluded": [{"id": "e", "title": "E", "url": "https://e", "reason": ""}]}]:
            with self.subTest(bundle=bundle), self.assertRaises(ValueError):
                self.run_apply(copy.deepcopy(bundle))

    def test_correction_keeps_original_collection_date(self):
        fixed = {**PAPER, "id": "old", "url": "https://x/old", "summary": "corrected"}
        self.run_apply({"date": "2026-10-16", "corrected": [{"paper": fixed, "qualityReview": REVIEW}]})
        self.assertEqual(self.catalogue["papers"][0]["addedAt"], "2026-10-01")
        self.assertEqual(self.decisions[0]["decision"], "existing")


if __name__ == "__main__":
    unittest.main()
