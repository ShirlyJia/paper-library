import { readFile } from 'node:fs/promises';
import { safeURL, paperPath, isFullDate, beijingDate } from '../library.js';
const catalogue = JSON.parse(await readFile(new URL('../data/papers.json', import.meta.url), 'utf8'));
const registry = JSON.parse(await readFile(new URL('../research/model-families.json', import.meta.url), 'utf8'));
const categories = new Set(catalogue.categories.map(c => c.id));
const ids = new Set(), urls = new Set();
const errors = [];
const identities = new Map();
function identitiesOf(paper) {
  const result = [];
  for (const value of [paper.id, paper.url, ...(paper.sources || [])]) {
    const arxiv = value.match(/(?:arxiv-|arxiv\.org\/(?:abs|pdf|html)\/)(\d{4}\.\d{4,5})(?:v\d+)?/i);
    if (arxiv) result.push(`arxiv:${arxiv[1]}`);
    if (/^https:\/\/openreview\.net\/(?:forum|pdf)\?/.test(value)) {
      const id = new URL(value).searchParams.get('id');
      if (id) result.push(`openreview:${id}`);
    }
    if (/^https:\/\/proceedings\.mlr\.press\/v\d+\/.+\.html$/.test(value)) result.push(value);
  }
  return new Set(result);
}
const nodeIds = new Set();
let sections = 0, topics = 0;
for (const category of catalogue.categories) {
  if (!category.description || !Array.isArray(category.questions) || category.questions.length < 1) errors.push(`${category.id} 缺少领域说明`);
  const visit = (node, depth) => {
    const key = String(node.id);
    if (!node.id || nodeIds.has(key)) errors.push(`目录 ID 重复或缺失: ${key}`);
    nodeIds.add(key);
    for (const field of ['name', 'description', 'code']) if (typeof node[field] !== 'string' || !node[field].trim()) errors.push(`${key} 缺少目录字段: ${field}`);
    if (depth < 3 && (!Array.isArray(node.children) || !node.children.length)) errors.push(`${key} 缺少下级目录`);
    if (depth === 2) sections++;
    if (depth === 3) { topics++; if (node.children) errors.push(`${key} 层级过深`); }
    for (const child of node.children || []) visit(child, depth + 1);
  };
  visit(category, 1);
}
for (const p of catalogue.papers) {
  if (!p.id || ids.has(p.id)) errors.push(`重复或缺失 ID: ${p.id}`);
  if (urls.has(p.url)) errors.push(`重复论文: ${p.url}`);
  ids.add(p.id); urls.add(p.url);
  for (const key of ['title', 'summary', 'venue', 'date', 'updated']) if (!p[key]?.trim()) errors.push(`${p.id} 缺少 ${key}`);
  for (const key of ['date', 'updated']) if (!/^\d{4}(-\d{2})?(-\d{2})?$/.test(p[key])) errors.push(`${p.id} 日期格式无效: ${key}`);
  if (!isFullDate(p.addedAt) || p.addedAt > beijingDate()) errors.push(`${p.id} 本站收录日期无效或在未来`);
  if (!categories.has(p.category)) errors.push(`${p.id} 分类不存在`);
  if (paperPath(p, catalogue.categories).length !== 3) errors.push(`${p.id} 子方向或具体议题不属于其上级目录`);
  if (!['published','preprint','workshop','report'].includes(p.status)) errors.push(`${p.id} 发表状态无效`);
  if (p.recognition) {
    if (!['Highlight','Spotlight','Oral','Spotlight Oral'].includes(p.recognition.label)) errors.push(`${p.id} 会议标记无效`);
    if (!['published','workshop'].includes(p.status)) errors.push(`${p.id} 未收录论文不能附会议标记`);
    if (!safeURL(p.recognition.source) || !/^\d{4}-\d{2}-\d{2}$/.test(p.recognition.verifiedAt || '')) errors.push(`${p.id} 会议标记缺少来源或核实日期`);
  }
  for (const key of ['url','pdf','code']) if ((p[key] || key === 'url') && !safeURL(p[key])) errors.push(`${p.id} 链接无效: ${key}`);
  for (const key of ['aliases','sources']) if (p[key] !== undefined && (!Array.isArray(p[key]) || p[key].some(v => typeof v !== 'string' || !v.trim()))) errors.push(`${p.id} ${key} 格式无效`);
  for (const url of p.sources || []) if (!safeURL(url)) errors.push(`${p.id} 核验来源无效`);
  for (const key of identitiesOf(p)) {
    if (identities.has(key) && identities.get(key) !== p.id) errors.push(`同一论文重复收录: ${identities.get(key)} / ${p.id} (${key})`);
    identities.set(key,p.id);
  }
  for (const word of ['优先阅读', '本轮', 'needs supplement', 'cross_core']) if (JSON.stringify(p).includes(word)) errors.push(`${p.id} 含过程性文字: ${word}`);
}
const paperById = new Map(catalogue.papers.map(p => [p.id, p]));
const historyDates = new Set(), firstAdded = new Set();
if (!Array.isArray(catalogue.collectionUpdates)) errors.push('缺少本站收录与更新记录');
for (const day of catalogue.collectionUpdates || []) {
  if (!isFullDate(day.date) || day.date > beijingDate() || day.date > catalogue.updatedAt || historyDates.has(day.date)) errors.push(`本站更新记录日期无效或重复: ${day.date}`);
  historyDates.add(day.date);
  for (const kind of ['added', 'updated']) {
    if (!Array.isArray(day[kind]) || new Set(day[kind]).size !== day[kind].length) { errors.push(`${day.date} ${kind} 记录无效或重复`); continue; }
    for (const id of day[kind]) {
      const paper = paperById.get(id);
      if (!paper) { errors.push(`更新记录引用不存在的论文: ${id}`); continue; }
      if (kind === 'added') {
        if (firstAdded.has(id) || paper.addedAt !== day.date) errors.push(`${id} 收录日期与记录不一致`);
        firstAdded.add(id);
      } else if (paper.addedAt >= day.date) errors.push(`${id} 更新记录不能早于或重复当天收录记录`);
    }
  }
  if (!day.added?.length && !day.updated?.length) errors.push(`${day.date} 为空更新记录`);
}
for (const id of ids) if (!firstAdded.has(id)) errors.push(`${id} 缺少首次收录记录`);
for (const family of registry.families) {
  if (!family.name || !family.paperIds?.length || !family.sources?.length) errors.push('模型家族缺少名称、论文或来源');
  for (const id of family.paperIds || []) if (!ids.has(id)) errors.push(`已知版本漏收: ${family.name} / ${id}`);
  for (const source of family.sources || []) if (!safeURL(source)) errors.push(`${family.name} 来源无效`);
}
if (errors.length) { console.error(errors.join('\n')); process.exit(1); }
console.log(`索引通过：${ids.size} 篇论文，${categories.size} 个领域 → ${sections} 个子方向 → ${topics} 个议题，${catalogue.papers.filter(p => p.pdf).length} 个 PDF 入口。`);
console.log(`覆盖检查通过：${registry.families.length} 个已登记模型家族，${registry.families.reduce((n,f) => n + f.paperIds.length,0)} 项论文版本。`);
