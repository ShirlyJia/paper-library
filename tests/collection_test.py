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

    def test_identical_titles_with_distinct_ids_remain_separate(self):
        records = [{'id':'arxiv-'+aid,'title':'Same title','sources':[],'discoveredVia':['arxiv']} for aid in ['2606.04485','2609.17488']]
        self.assertEqual(len(collect.merge_candidates(records,[])),2)

    def test_new_revision_reopens_a_previously_deferred_candidate(self):
        old = {'id':'arxiv-2609.25541','decision':'deferred','sourceUpdated':'2026-09-22'}
        candidate = {'id':'arxiv-2609.25541','updated':'2026-10-12','existingIds':[],'reviewState':'needs-review'}
        collect.apply_decisions([candidate],[old])
        self.assertEqual(candidate['reviewState'],'needs-review')
        candidate['updated']='2026-09-22'
        collect.apply_decisions([candidate],[old])
        self.assertEqual(candidate['reviewState'],'deferred')


if __name__ == '__main__':
    unittest.main()
