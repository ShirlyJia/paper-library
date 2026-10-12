import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { filterPapers, readState, stateSearch, sixMonthsAgo, safeURL, toCSV, scopePath, paperPath, normalizeScope, belongsTo } from '../library.js';
const catalogue = JSON.parse(await readFile(new URL('../data/papers.json', import.meta.url), 'utf8'));
const { papers, categories } = catalogue;
const options = { categories, now: new Date('2026-10-12T12:00:00Z') };

test('search combines English model names and Chinese concepts', () => {
  const fixtures = [
    { id: 'both', title: 'TabPFN Adaptation', summary: '研究表格模型的微调方法。' },
    { id: 'english-only', title: 'TabPFN Inference', summary: '研究推理效率。' },
    { id: 'chinese-only', title: 'Other Model', summary: '研究微调方法。' },
  ];
  const result = filterPapers(fixtures, { ...readState(), query: 'tabpfn 微调' }, options);
  assert.deepEqual(result.map(p => p.id), ['both']);
});
test('search finds model aliases absent from the paper title within the requested scope', () => {
  for (const query of ['LimiX2M', 'LimiX 2M', 'RaBEL']) {
    const matches = filterPapers(papers, { ...readState(), query }, options);
    assert.ok(matches.some(p => p.id === 'arxiv-2606.04485'));
  }
  const retro = filterPapers(papers, { ...readState(), query:'Retro' }, options);
  assert.ok(retro.some(p => p.id === 'arxiv-2610.10317'));
  const scoped = filterPapers(papers, { ...readState(), category:1, section:'industry-models', topic:'tabular-releases', period:'2026', query:'TAFFY' }, options);
  assert.deepEqual(scoped.map(p=>p.id),['arxiv-2610.07559']);
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
  const original = { ...readState(), query: '因果 TabPFN', category: 3, section: 'causal-estimation', topic: 'continuous-iv', status: 'published', period: '2026', codeOnly: true, page: 2 };
  assert.deepEqual(readState(stateSearch(original)), original);
  const invalid = readState('?category=NaN&status=anything&sort=no&page=-100');
  assert.equal(invalid.category, 0); assert.equal(invalid.status, 'all'); assert.equal(invalid.page, 1);
});

test('all papers have exactly one complete path and child counts sum to their parent', () => {
  assert.ok(papers.every(p => paperPath(p, categories).length === 3));
  for (const category of categories) {
    const parents = papers.filter(p => belongsTo(p, category));
    assert.equal(category.children.reduce((n, s) => n + papers.filter(p => belongsTo(p, s)).length, 0), parents.length);
    for (const section of category.children) {
      assert.equal(section.children.reduce((n, t) => n + papers.filter(p => belongsTo(p, t)).length, 0), papers.filter(p => belongsTo(p, section)).length);
    }
  }
});

test('topic scope narrows its parent and respects other filters', () => {
  const state = { ...readState(), category: 3, section: 'causal-estimation', topic: 'continuous-iv' };
  const result = filterPapers(papers, state, options);
  assert.deepEqual(new Set(result.map(p => p.id)), new Set(['arxiv-2605.15133', 'arxiv-2605.05993']));
  assert.ok(filterPapers(papers, { ...state, codeOnly: true }, options).every(p => p.code));
  const path = scopePath(categories, state);
  assert.deepEqual(path.map(n => n.name), ['结构化数据的因果分析与决策', '基于结构化数据的因果推断', '连续处理与工具变量']);
  assert.ok(toCSV(result, categories).includes('基于结构化数据的因果推断'));
});

test('invalid child links fall back to the nearest valid ancestor', () => {
  const state = { ...readState(), category: 3, section: 'causal-estimation', topic: 'schema-matching', query: '因果' };
  const fixed = normalizeScope(state, categories);
  assert.equal(fixed.topic, ''); assert.equal(fixed.section, 'causal-estimation'); assert.equal(fixed.query, '因果');
  const wrongBranch = normalizeScope({ ...state, section: 'industry-models' }, categories);
  assert.equal(wrongBranch.category, 3); assert.equal(wrongBranch.section, ''); assert.equal(wrongBranch.topic, '');
});

test('category titles retain the original paper list wording', () => {
  assert.deepEqual(categories.map(c => c.name), [
    '结构化数据模型的业界进展', '表格预测与决策优化', '结构化数据的因果分析与决策',
    '语义结构化与表格特征构建', '表格模型的上下文学习与推理优化', '表格基础模型的微调与蒸馏',
  ]);
});
test('external links reject executable schemes; CSV preserves quotes and blocks formula execution', () => {
  assert.equal(safeURL('javascript:alert(1)'), null);
  assert.equal(safeURL('https://arxiv.org/abs/2610.12005'), 'https://arxiv.org/abs/2610.12005');
  const text = toCSV([{ ...papers[0], title: '=test,"quoted"' }], categories);
  assert.ok(text.startsWith('\uFEFF')); assert.ok(text.includes('"\'=test,""quoted"""'));
});
