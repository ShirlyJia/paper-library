import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('collect', Path(__file__).resolve().parents[1] / 'scripts/collect.py')
collect = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collect)


class CollectionTests(unittest.TestCase):
    def test_conference_titles_are_read_from_entries_not_link_labels(self):
        parser = collect.Proceedings()
        parser.feed('<div class="paper"><p class="title">Model &amp; Method</p><p class="links"><a href="https://proceedings.mlr.press/v306/a.html">abs</a></p></div>')
        self.assertEqual(parser.records, [{'title':'Model & Method','sources':['https://proceedings.mlr.press/v306/a.html']}])

    def test_atom_preserves_first_publication_and_revision(self):
        entries, total = collect.parse_atom('''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
        <opensearch:totalResults>201</opensearch:totalResults><entry><id>http://arxiv.org/abs/2606.04485v2</id>
        <title>LimiX-2M</title><published>2026-06-03T00:00:00Z</published><updated>2026-06-04T00:00:00Z</updated><summary>Two million parameters</summary></entry></feed>''')
        self.assertEqual(total,201)
        self.assertEqual(entries[0]['id'],'arxiv-2606.04485')
        self.assertEqual(entries[0]['date'],'2026-06-03')
        self.assertEqual(entries[0]['updated'],'2026-06-04')

    def test_versions_and_renamed_conference_entry_merge_without_merging_models(self):
        records = [
            {'title':'Old title','url':'https://arxiv.org/abs/2606.04485v1','sources':[],'discoveredVia':['arxiv']},
            {'title':'LimiX-2M','url':'https://proceedings.mlr.press/v306/wang26kw.html','sources':['https://arxiv.org/pdf/2606.04485'],'discoveredVia':['conference']},
            {'title':'LimiX-2','url':'https://arxiv.org/abs/2609.17488','sources':[],'discoveredVia':['arxiv']},
        ]
        papers = [{'id':'kept-id','title':'LimiX-2M','url':'https://arxiv.org/abs/2606.04485'}]
        merged = collect.merge_candidates(records,papers)
        self.assertEqual(len(merged),2)
        self.assertEqual(next(p for p in merged if p['existingIds'])['existingIds'],['kept-id'])
        self.assertEqual(set(next(p for p in merged if p['existingIds'])['discoveredVia']),{'arxiv','conference'})

    def test_openreview_pdf_and_forum_resolve_to_the_same_work(self):
        a = collect.keys({'url':'https://openreview.net/pdf?id=work123'})
        b = collect.keys({'url':'https://openreview.net/forum?id=work123&noteId=review456'})
        self.assertTrue(a & b)
        self.assertEqual(collect.arxiv_id('https://arxiv.org/html/2610.07559v1'),'2610.07559')

    def test_doi_only_screening_records_accept_null_ids(self):
        record = {'id': None, 'url': 'https://doi.org/10.1234/example', 'sources': None}
        identities = collect.keys(record)
        self.assertIn('doi:10.1234/example', identities)
        self.assertEqual(collect.keys({'id': None, 'url': None, 'sources': [None]}), set())

    def test_identical_titles_with_distinct_ids_remain_separate(self):
        records = [{'id':'arxiv-'+aid,'title':'Same title','sources':[],'discoveredVia':['arxiv']} for aid in ['2606.04485','2609.17488']]
        self.assertEqual(len(collect.merge_candidates(records,[])),2)

    def test_missing_openalex_dates_and_titles_do_not_drop_candidates(self):
        records = [
            {'url': 'https://openalex.org/W1', 'title': None, 'date': None},
            {'url': 'https://openalex.org/W2', 'title': 'Undated work'},
            {'url': 'https://openalex.org/W3', 'title': 'Dated work', 'date': '2026-10-15'},
        ]
        merged = collect.merge_candidates(records, [])
        self.assertEqual([p['url'] for p in merged], [records[i]['url'] for i in (2, 1, 0)])
        self.assertIsNone(merged[-1]['date'])

    def test_new_revision_reopens_a_previously_deferred_candidate(self):
        old = {'id':'arxiv-2609.25541','decision':'deferred','sourceUpdated':'2026-09-22'}
        candidate = {'id':'arxiv-2609.25541','updated':'2026-10-12','existingIds':[],'reviewState':'needs-review'}
        collect.apply_decisions([candidate],[old])
        self.assertEqual(candidate['reviewState'],'needs-review')
        candidate['updated']='2026-09-22'
        collect.apply_decisions([candidate],[old])
        self.assertEqual(candidate['reviewState'],'deferred')

    def test_unknown_revision_dates_preserve_the_previous_decision(self):
        missing = object()
        for decision in ('deferred', 'excluded'):
            for updated in (missing, None, '', '2026-10-25'):
                for source_updated in (missing, None, '', '2026-10-01'):
                    if isinstance(updated, str) and updated and isinstance(source_updated, str) and source_updated:
                        continue  # Known dates are covered by the revision test above.
                    with self.subTest(decision=decision, updated=updated, source_updated=source_updated):
                        previous = {'url': 'https://example.org/undated-report', 'decision': decision}
                        candidate = {'url': 'https://example.org/undated-report', 'existingIds': [], 'reviewState': 'needs-review'}
                        if updated is not missing:
                            candidate['updated'] = updated
                        if source_updated is not missing:
                            previous['sourceUpdated'] = source_updated
                        original = dict(previous)
                        collect.apply_decisions([candidate], [previous])
                        self.assertEqual(candidate['reviewState'], decision)
                        self.assertEqual(previous, original)
                        self.assertEqual(candidate.get('updated', missing), updated)

    def test_undated_included_and_existing_candidates_keep_their_review_paths(self):
        previous = {'url': 'https://example.org/undated-report', 'decision': 'included', 'sourceUpdated': None}
        candidate = {'url': 'https://example.org/undated-report', 'updated': None, 'existingIds': [], 'reviewState': 'needs-review'}
        collect.apply_decisions([candidate], [previous])
        self.assertEqual(candidate['reviewState'], 'needs-review')
        candidate.update(existingIds=['catalogue-id'], reviewState='existing-check-update')
        collect.apply_decisions([candidate], [previous])
        self.assertEqual(candidate['reviewState'], 'existing-check-update')


    def test_family_queries_split_aliases_and_require_context_for_ambiguous_names(self):
        lanes, names = collect.family_queries([{'name': 'ConTextTab / SAP-RPT-1-OSS'}, {'name': 'Retro', 'needsContext': True}])
        query = ' OR '.join(lane['query'] for lane in lanes)
        self.assertIn('all:"ConTextTab"', query)
        self.assertIn('all:"SAP-RPT-1-OSS"', query)
        self.assertNotIn(' / ', query)
        self.assertIn('(all:"Retro" AND (all:tabular', query)
        self.assertEqual(names, ['ConTextTab', 'SAP-RPT-1-OSS'])

    def test_cache_pruning_keeps_fresh_responses(self):
        import os, tempfile, time
        with tempfile.TemporaryDirectory() as folder:
            old, new = Path(folder, 'old.txt'), Path(folder, 'new.txt')
            old.write_text('x'); new.write_text('y')
            os.utime(old, (time.time() - 3 * 86400,) * 2)
            collect.prune_cache(Path(folder))
            self.assertEqual([p.name for p in Path(folder).iterdir()], ['new.txt'])

    def test_local_setting_reads_env_file_without_quotes(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, '.env')
            path.write_text('# note\nOPENALEX_API_KEY="abc123"\n')
            self.assertEqual(collect.local_setting('OPENALEX_API_KEY', path), 'abc123')
            self.assertEqual(collect.local_setting('OTHER', path), '')

if __name__ == '__main__':
    unittest.main()
