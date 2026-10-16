import importlib.util
import json
import unittest
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

spec = importlib.util.spec_from_file_location('discovery', Path(__file__).resolve().parents[1] / 'scripts/discovery.py')
discovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(discovery)


class DiscoveryTests(unittest.TestCase):
    def scanner(self, fetch=lambda url: '', max_pages=2, papers=None):
        return discovery.Discovery({'relevancePattern': 'tabular', 'citationSeeds': []}, fetch,
                                   date(2026, 4, 13), date(2026, 10, 13), max_pages, papers or [], lambda run: None)

    def test_nested_bibtex_and_abstract_only_match(self):
        raw = '''@InProceedings{p,
          title = {A {General} Method},
          url = {https://proceedings.mlr.press/v306/p.html},
          abstract = {We improve {tabular} prediction without changing the title.},
          year = {2026}
        }'''
        records = discovery.parse_bibliography(raw, 'ICML 2026')
        scanner = self.scanner()
        self.assertEqual(scanner.retain(records, 'official'), 1)
        self.assertEqual(records[0]['title'], 'A General Method')
        self.assertEqual(records[0]['retrievalEvidence'], ['official-metadata:abstract'])
        self.assertEqual(records[0]['sources'], ['https://proceedings.mlr.press/v306/p.html'])

    def test_volume_year_can_be_outside_the_anchor(self):
        raw = '<li><a href="v306"><b>Volume 306</b></a> Proceedings of ICML 2026</li>'
        self.assertEqual(discovery.pmlr_volumes(raw, 2025, 2026, 'ICML')[0]['url'],
                         'https://proceedings.mlr.press/v306/')

    def test_programme_abstract_map_and_track_are_preserved(self):
        source = {'origin': 'https://iclr.cc', 'name': 'ICLR'}
        data = {'count': 1, 'results': [{'id': 1, 'name': 'A method', 'paper_url': 'https://openreview.net/forum?id=x',
                'sourceurl': 'https://openreview.net/group?id=ICLR.cc/2026/Conference', 'decision': 'Accept (Poster)'}]}
        records = discovery.parse_programme(data, {'1': 'Tabular examples.'}, source, 2026)
        self.assertEqual(records[0]['abstract'], 'Tabular examples.')
        self.assertTrue(records[0]['venueTrack'].endswith('/Conference'))
        self.assertEqual(records[0]['sources'], ['https://openreview.net/forum?id=x'])
        data['count'] = 2
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            discovery.parse_programme(data, {}, source, 2026)

    def test_programme_without_paper_link_keeps_individual_official_page(self):
        data = [{'id': 1, 'name': 'Tabular examples', 'abstract': 'body', 'virtualsite_url': '/virtual/2026/poster/1'}]
        records = discovery.parse_programme(data, {}, {'origin': 'https://iclr.cc', 'name': 'ICLR'}, 2026)
        self.assertEqual(records[0]['url'], 'https://iclr.cc/virtual/2026/poster/1')

    def test_acl_nested_markup_and_front_matter(self):
        raw = '''<collection id="2026.acl"><volume id="long"><meta><booktitle>ACL</booktitle><year>2026</year><month>July</month></meta>
        <paper id="0"><title>Proceedings</title></paper><paper id="1"><title>A <fixed-case>New</fixed-case> Method</title>
        <abstract>For <fixed-case>tabular</fixed-case> data.</abstract></paper></volume></collection>'''
        papers = discovery.parse_anthology(raw)
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]['title'], 'A New Method')
        self.assertEqual(papers[0]['abstract'], 'For tabular data.')
        self.assertEqual(papers[0]['venueDate'], '2026-07')

    def work(self, number=1):
        return {'id': f'https://openalex.org/W{number}', 'title': 'No keyword in this title',
                'publication_date': '2026-05-01', 'abstract_inverted_index': {'Some': [0], 'method.': [1]}}

    def test_semantic_results_are_not_discarded_by_keyword_filter(self):
        def fetch(url):
            params = parse_qs(urlparse(url).query)
            self.assertNotIn('cursor', params)
            return json.dumps({'meta': {'count': 50}, 'results': [self.work()]})
        scanner = self.scanner(fetch)
        scanner.alex_pages({'search.semantic': 'meaning'}, 'semantic', semantic=True)
        self.assertEqual(len(scanner.records), 1)
        self.assertEqual(scanner.records[0]['abstract'], 'Some method.')
        self.assertEqual(scanner.runs[0]['coverage'], 'ranked-top-50')

    def test_cursor_pagination_and_partial_failure_are_visible(self):
        calls = []
        def fetch(url):
            cursor = parse_qs(urlparse(url).query)['cursor'][0]
            calls.append(cursor)
            if len(calls) == 2:
                raise RuntimeError('Rate limited')
            return json.dumps({'meta': {'count': 101, 'next_cursor': 'next'}, 'results': [self.work()]})
        scanner = self.scanner(fetch)
        scanner.alex_pages({'search': 'tabular'}, 'fulltext')
        self.assertEqual(calls, ['*', 'next'])
        self.assertEqual(len(scanner.records), 1)
        self.assertEqual(scanner.runs[0]['status'], 'failed')
        self.assertEqual(scanner.runs[0]['nextCursor'], 'next')

    def test_page_cap_is_not_reported_as_complete(self):
        scanner = self.scanner(lambda url: json.dumps({'meta': {'count': 200, 'next_cursor': 'next'},
                                                        'results': [self.work()]}), max_pages=1)
        scanner.alex_pages({'search': 'tabular'}, 'fulltext')
        self.assertEqual(scanner.runs[0]['status'], 'truncated')

    def test_citation_neighbors_keep_papers_without_matching_terms(self):
        scanner = self.scanner(lambda url: json.dumps({'meta': {'count': 1}, 'results': [self.work(2)]}),
                               papers=[{'title': 'Known'}])
        scanner.records.append({'title': 'Known', 'openalexId': 'https://openalex.org/W1',
                                'referencedWorks': ['https://openalex.org/W3']})
        scanner.citations()
        self.assertTrue(any(p.get('discoveredVia') == ['openalex:incoming-citations'] for p in scanner.records))
        self.assertTrue(any(p.get('discoveredVia') == ['openalex:references'] for p in scanner.records))

    def test_resume_continues_cursor_instead_of_repeating_top_results(self):
        def fetch(url):
            self.assertEqual(parse_qs(urlparse(url).query)['cursor'], ['saved-cursor'])
            return json.dumps({'meta': {'count': 101, 'next_cursor': None}, 'results': [self.work(101)]})
        scanner = self.scanner(fetch)
        scanner.config['_resumeRuns'] = [{'source': 'fulltext', 'status': 'truncated', 'count': 100,
                                          'query': {'search': 'tabular'}, 'nextCursor': 'saved-cursor'}]
        scanner.alex_pages({'search': 'tabular'}, 'fulltext')
        self.assertEqual(scanner.runs[0]['count'], 101)
        self.assertEqual(scanner.runs[0]['status'], 'complete')

    def test_without_api_key_only_the_first_page_is_requested(self):
        calls = []
        def fetch(url):
            calls.append(url)
            return json.dumps({'meta': {'count': 300, 'next_cursor': 'next'}, 'results': [self.work()]})
        scanner = self.scanner(fetch, max_pages=5)
        scanner.keyed = False
        scanner.alex_pages({'search': 'tabular'}, 'fulltext')
        self.assertEqual(len(calls), 1)
        self.assertEqual((scanner.runs[0]['status'], scanner.runs[0]['nextCursor']), ('truncated', 'next'))
        self.assertIn('OPENALEX_API_KEY', scanner.runs[0]['error'])
        scanner.config['_resumeRuns'] = [{'source': 'resumed', 'status': 'truncated', 'count': 100,
                                          'query': {'search': 'tabular'}, 'nextCursor': 'saved'}]
        scanner.alex_pages({'search': 'tabular'}, 'resumed')
        self.assertEqual(len(calls), 1)

    def test_acl_event_only_collection_is_not_a_parser_failure(self):
        self.assertEqual(discovery.parse_anthology('<collection id="2025.aacl"><event id="aacl-2025"/></collection>'), [])
        with self.assertRaises(ValueError):
            discovery.parse_anthology('<unexpected/>')

    def test_tmlr_acceptance_does_not_overwrite_first_release_date(self):
        raw = '<li class="item nocertificate"><h4><a><b>A tabular method</b></a></h4><p><i>Authors</i>, October 2026 <a href="https://openreview.net/forum?id=x">openreview</a></p></li>'
        paper = discovery.parse_tmlr(raw, 2025, 2026)[0]
        self.assertEqual(paper['venueDate'], '2026-10')
        self.assertEqual(paper['officialDecision'], 'Accepted')
        self.assertNotIn('date', paper)
        self.assertNotIn('https://jmlr.org/tmlr/papers/', paper['sources'])


if __name__ == '__main__':
    unittest.main()
