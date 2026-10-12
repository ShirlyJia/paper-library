import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { filterPapers, readState, stateSearch, sixMonthsAgo, safeURL, toCSV } from '../library.js';
const catalogue = JSON.parse(await readFile(new URL('../data/papers.json', import.meta.url), 'utf8'));
const { papers, categories } = catalogue;
const options = { categories, now: new Date('2026-10-12T12:00:00Z') };

test('search combines English model names and Chinese concepts', () => {
  const result = filterPapers(papers, { ...readState(), query: 'TabPFN 微调' }, options);
  assert.ok(result.length > 0);
  assert.ok(result.every(p => `${p.title} ${p.summary} ${p.evidence}`.toLowerCase().includes('tabpfn')));
});
test('recent filter uses first publication, not revisions or a year-only date', () => {
  const fixtures = [
    { id: 'recent', title: 'Recent', date: '2026-04-12', updated: '2026-04-12' },
    { id: 'revised', title: 'Revised', date: '2026-04-11', updated: '2026-10-12' },
    { id: 'year-only', title: 'Year only', date: '2026', updated: '2026' },
    { id: 'future', title: 'Future', date: '2026-10-13', updated: '2026-10-13' },
  ];
  const result = filterPapers(fixtures, { ...readState(), period: '6m' }, options);
  assert.deepEqual(result.map(p => p.id), ['recent']);
  assert.equal(sixMonthsAgo(new Date('2026-08-31T00:00:00Z')), '2026-02-28');
});
test('category, publication, code and saved filters intersect', () => {
  const saved = new Set(papers.map(p => p.id));
  const result = filterPapers(papers, { ...readState(), category: 4, status: 'published', codeOnly: true, savedOnly: true }, { ...options, saved });
  assert.ok(result.length > 0);
  assert.ok(result.every(p => p.category === 4 && p.status === 'published' && p.code));
  assert.deepEqual(filterPapers(papers, { ...readState(), savedOnly: true }, options), []);
});
test('shareable filters round-trip, invalid input falls back safely', () => {
  const original = { ...readState(), query: '因果 TabPFN', category: 3, status: 'published', period: '2026', codeOnly: true, page: 2 };
  assert.deepEqual(readState(stateSearch(original)), original);
  const invalid = readState('?category=NaN&status=anything&sort=no&page=-100');
  assert.equal(invalid.category, 0); assert.equal(invalid.status, 'all'); assert.equal(invalid.page, 1);
});
test('external links reject executable schemes; CSV preserves quotes and blocks formula execution', () => {
  assert.equal(safeURL('javascript:alert(1)'), null);
  assert.equal(safeURL('https://arxiv.org/abs/2610.12005'), 'https://arxiv.org/abs/2610.12005');
  const text = toCSV([{ ...papers[0], title: '=test,"quoted"' }], categories);
  assert.ok(text.startsWith('\uFEFF')); assert.ok(text.includes('"\'=test,""quoted"""'));
});
