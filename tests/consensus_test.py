import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from import_consensus import normalize_export
from collect import merge_candidates


class ConsensusImportTests(unittest.TestCase):
    def bundle(self, fetched=False):
        hit = {'id': 'paper-id', 'title': 'A tabular method', 'text': 'Search excerpt...',
               'url': 'https://consensus.app/papers/details/paper-id/?utm_source=chatgpt'}
        return {'searches': [{'id': 'models', 'query': 'query', 'status': 'complete', 'results': [hit]}],
                'papers': [{**hit, 'text': 'Full abstract', 'metadata': {'publish_year': '2026'}}] if fetched else []}

    def test_search_excerpt_is_not_a_fetched_abstract_or_acceptance_proof(self):
        records, runs = normalize_export(self.bundle())
        self.assertNotIn('abstract', records[0])
        self.assertNotIn('status', records[0])
        self.assertEqual(records[0]['fetchState'], 'pending')
        self.assertEqual(runs[0]['pendingFetchIds'], ['paper-id'])

    def test_fetched_year_is_not_fabricated_into_an_exact_date(self):
        records, _ = normalize_export(self.bundle(True))
        self.assertEqual(records[0]['date'], '2026')
        self.assertEqual(records[0]['abstract'], 'Full abstract')
        self.assertTrue(records[0]['needsPrimaryVerification'])
        self.assertNotIn('utm_source', records[0]['url'])

    def test_rate_limit_is_a_failed_source_not_an_empty_success(self):
        records, runs = normalize_export({'searches': [{'id': 'models', 'query': 'query',
                'status': 'failed', 'error': 'Rate limit exceeded'}]})
        self.assertEqual(records, [])
        self.assertEqual(runs[0]['status'], 'failed')
        self.assertIn('Rate limit', runs[0]['error'])

    def test_renamed_fetch_record_deduplicates_by_provider_id(self):
        records, _ = normalize_export(self.bundle())
        revised = {**records[0], 'title': 'Renamed paper', 'url': 'https://consensus.app/papers/new/paper-id/',
                   'sources': ['https://consensus.app/papers/new/paper-id/']}
        self.assertEqual(len(merge_candidates([records[0], revised], [])), 1)
