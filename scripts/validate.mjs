import { readFile } from 'node:fs/promises';
import { safeURL, paperPath } from '../library.js';
const catalogue = JSON.parse(await readFile(new URL('../data/papers.json', import.meta.url), 'utf8'));
const categories = new Set(catalogue.categories.map(c => c.id));
const ids = new Set(), urls = new Set();
const errors = [];
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
  if (!categories.has(p.category)) errors.push(`${p.id} 分类不存在`);
  if (paperPath(p, catalogue.categories).length !== 3) errors.push(`${p.id} 子方向或具体议题不属于其上级目录`);
  if (!['published','preprint','workshop','report'].includes(p.status)) errors.push(`${p.id} 发表状态无效`);
  if (p.recognition) {
    if (!['Highlight','Spotlight','Oral','Spotlight Oral'].includes(p.recognition.label)) errors.push(`${p.id} 会议标记无效`);
    if (!['published','workshop'].includes(p.status)) errors.push(`${p.id} 未收录论文不能附会议标记`);
    if (!safeURL(p.recognition.source) || !/^\d{4}-\d{2}-\d{2}$/.test(p.recognition.verifiedAt || '')) errors.push(`${p.id} 会议标记缺少来源或核实日期`);
  }
  for (const key of ['url','pdf','code']) if ((p[key] || key === 'url') && !safeURL(p[key])) errors.push(`${p.id} 链接无效: ${key}`);
  for (const word of ['优先阅读', '本轮', 'needs supplement', 'cross_core']) if (JSON.stringify(p).includes(word)) errors.push(`${p.id} 含过程性文字: ${word}`);
}
if (errors.length) { console.error(errors.join('\n')); process.exit(1); }
console.log(`索引通过：${ids.size} 篇论文，${categories.size} 个领域 → ${sections} 个子方向 → ${topics} 个议题，${catalogue.papers.filter(p => p.pdf).length} 个 PDF 入口。`);
