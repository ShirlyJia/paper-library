import { readFile, writeFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { beijingDate, isFullDate } from '../library.js';

const contentFields = ['title', 'date', 'dateNote', 'updated', 'summary', 'category', 'section', 'topicId', 'related', 'topic', 'status', 'venue', 'url', 'pdf', 'code', 'keywords', 'aliases', 'sources'];

export function paperContent(paper) {
  const values = contentFields.map(key => Array.isArray(paper[key]) ? [...new Set(paper[key])].sort() : paper[key] ?? null);
  values.push(paper.recognition?.label ?? null, paper.recognition?.source ?? null);
  return JSON.stringify(values);
}

export function recordUpdates(catalog, previous, date = beijingDate()) {
  if (!isFullDate(date)) throw new Error('收录日期必须为有效的 YYYY-MM-DD。');
  const old = new Map(previous.papers.map(p => [p.id, p]));
  const added = [], updated = [];
  for (const paper of catalog.papers) {
    const prior = old.get(paper.id);
    if (!prior) {
      paper.addedAt = date;
      added.push(paper.id);
    } else {
      if (prior.addedAt && paper.addedAt && prior.addedAt !== paper.addedAt) throw new Error(`${paper.id} 的历史收录日期不能随资料更新改写。`);
      paper.addedAt = prior.addedAt || paper.addedAt;
      if (!isFullDate(paper.addedAt)) throw new Error(`${paper.id} 缺少已核实的历史收录日期。`);
      if (date < paper.addedAt) throw new Error(`${paper.id} 的更新日期不能早于收录日期。`);
      if (paperContent(paper) !== paperContent(prior)) updated.push(paper.id);
    }
  }
  if (!added.length && !updated.length) return { added, updated };
  catalog.collectionUpdates ||= [];
  let day = catalog.collectionUpdates.find(event => event.date === date);
  if (!day) { day = { date, added: [], updated: [] }; catalog.collectionUpdates.push(day); }
  day.added = [...new Set([...day.added, ...added])].sort();
  day.updated = [...new Set([...day.updated, ...updated])].filter(id => !day.added.includes(id)).sort();
  catalog.collectionUpdates.sort((a, b) => a.date.localeCompare(b.date));
  catalog.updatedAt = [catalog.updatedAt, date].sort().at(-1);
  return { added, updated };
}

async function main() {
  const args = process.argv.slice(2);
  let base = 'HEAD', date = beijingDate();
  for (let i = 0; i < args.length; i += 2) {
    if (!['--base', '--date'].includes(args[i]) || !args[i + 1]) throw new Error('用法：npm run record:updates -- [--base Git引用] [--date YYYY-MM-DD]');
    if (args[i] === '--base') base = args[i + 1]; else date = args[i + 1];
  }
  const root = fileURLToPath(new URL('../', import.meta.url));
  const path = new URL('../data/papers.json', import.meta.url);
  const before = await readFile(path, 'utf8');
  const catalog = JSON.parse(before);
  const previous = JSON.parse(execFileSync('git', ['show', `${base}:data/papers.json`], { cwd: root, encoding: 'utf8', maxBuffer: 20 * 1024 * 1024 }));
  const result = recordUpdates(catalog, previous, date);
  const after = JSON.stringify(catalog, null, 2) + '\n';
  if (after !== before) await writeFile(path, after);
  console.log(`本站收录记录：新增 ${result.added.length} 篇，资料更新 ${result.updated.length} 篇；日期 ${date}。`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}
