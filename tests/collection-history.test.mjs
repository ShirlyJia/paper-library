import test from 'node:test';
import assert from 'node:assert/strict';
import { recordUpdates } from '../scripts/record-updates.mjs';
import { beijingDate, recentCollectionUpdates, filterPapers, readState, stateSearch } from '../library.js';

const categories = [1, 2].map(id => ({ id, code: `0${id}`, name: `方向 ${id}`, children: [
  { id: `section-${id}`, code: `0${id}.01`, name: `子方向 ${id}`, children: [
    { id: `topic-${id}`, code: `0${id}.01.01`, name: `议题 ${id}` },
  ] },
] }));
const paper = (id, category = 1) => ({ id, title: id, date: '2020-01-01', updated: '2020-01-01', addedAt: '2026-10-12', category, section: `section-${category}`, topicId: `topic-${category}`, summary: '原始介绍' });
const catalog = () => ({ updatedAt: '2026-10-12', categories, papers: [paper('old')], collectionUpdates: [{ date: '2026-10-12', added: ['old'], updated: [] }] });

test('collection dates remain separate from publication and revision dates', () => {
  const previous = catalog(), current = structuredClone(previous);
  current.papers[0].summary = '补充经核实的实验限制';
  current.papers.push({ ...paper('backfill'), addedAt: undefined });
  assert.deepEqual(recordUpdates(current, previous, '2026-10-14'), { added: ['backfill'], updated: ['old'] });
  assert.equal(current.papers[0].addedAt, '2026-10-12');
  assert.equal(current.papers[1].addedAt, '2026-10-14');
  assert.ok(current.papers.every(p => p.date === '2020-01-01' && p.updated === '2020-01-01'));
  assert.deepEqual(current.collectionUpdates.at(-1), { date: '2026-10-14', added: ['backfill'], updated: ['old'] });
});

test('repeated runs and changes to a paper on its collection day do not inflate activity', () => {
  const previous = catalog(), current = structuredClone(previous);
  current.papers[0].summary = '更新介绍';
  recordUpdates(current, previous, '2026-10-12');
  recordUpdates(current, previous, '2026-10-12');
  assert.deepEqual(current.collectionUpdates, previous.collectionUpdates);
  const before = JSON.stringify(current);
  recordUpdates(current, structuredClone(current), '2026-10-15');
  assert.equal(JSON.stringify(current), before);
});

test('verification stamps and source ordering alone do not create content updates', () => {
  const previous = catalog();
  Object.assign(previous.papers[0], { sources: ['https://a.test','https://b.test'], recognition: {label:'Spotlight',source:'https://a.test',verifiedAt:'2026-10-12'} });
  const current = structuredClone(previous);
  current.papers[0].sources.reverse(); current.papers[0].recognition.verifiedAt = '2026-10-14';
  assert.deepEqual(recordUpdates(current, previous, '2026-10-14'), {added:[],updated:[]});
  assert.equal(current.updatedAt, '2026-10-12');
  assert.throws(() => recordUpdates(current, previous, '2026-02-30'), /有效/);
  current.papers[0].addedAt = '2026-10-14';
  assert.throws(() => recordUpdates(current, previous, '2026-10-14'), /不能随资料更新改写/);
});

test('activity uses Beijing dates, includes the 30-day boundary and excludes future events', () => {
  const now = new Date('2026-10-13T16:00:00Z');
  assert.equal(beijingDate(now), '2026-10-14');
  const data = { categories, papers: [paper('one'),paper('two',2)], collectionUpdates: [
    {date:'2026-09-14',added:['one'],updated:[]},
    {date:'2026-09-15',added:['two'],updated:[]},
    {date:'2026-10-14',added:['one'],updated:['two']},
    {date:'2026-10-15',added:[],updated:['one']},
  ] };
  const days = recentCollectionUpdates(data, readState(), {now});
  assert.deepEqual(days.map(d=>[d.date,d.added,d.updated]), [['2026-10-14',1,1],['2026-09-15',1,0]]);
  const scoped = recentCollectionUpdates(data, {...readState(),category:2,section:'section-2'}, {now});
  assert.equal(scoped[0].added,0); assert.equal(scoped[0].updated,1);
  assert.equal(scoped[0].groups[0].path.at(-1).id,'topic-2');
  assert.deepEqual(recentCollectionUpdates(data, readState(), {now:new Date('2027-01-01')}),[]);
});

test('recent collection sorting is shareable and does not change default publication sorting', () => {
  const papers = [ {...paper('new-publication'),date:'2026-10-10'}, {...paper('older-backfill'),date:'2018-01-01',addedAt:'2026-10-14'} ];
  assert.equal(filterPapers(papers,readState())[0].id,'new-publication');
  const state = {...readState(),sort:'added'};
  assert.equal(filterPapers(papers,state)[0].id,'older-backfill');
  assert.equal(readState(stateSearch(state)).sort,'added');
});
