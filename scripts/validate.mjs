import { readFile } from 'node:fs/promises';
import { safeURL } from '../library.js';
const catalogue = JSON.parse(await readFile(new URL('../data/papers.json', import.meta.url), 'utf8'));
const categories = new Set(catalogue.categories.map(c => c.id));
const ids = new Set(), urls = new Set();
const errors = [];
for (const p of catalogue.papers) {
  if (!p.id || ids.has(p.id)) errors.push(`重复或缺失 ID: ${p.id}`);
  if (urls.has(p.url)) errors.push(`重复论文: ${p.url}`);
  ids.add(p.id); urls.add(p.url);
  for (const key of ['title', 'summary', 'evidence', 'venue', 'date', 'updated']) if (!p[key]?.trim()) errors.push(`${p.id} 缺少 ${key}`);
  for (const key of ['date', 'updated']) if (!/^\d{4}(-\d{2})?(-\d{2})?$/.test(p[key])) errors.push(`${p.id} 日期格式无效: ${key}`);
  if (!categories.has(p.category)) errors.push(`${p.id} 分类不存在`);
  if (!['published','preprint','workshop','report'].includes(p.status)) errors.push(`${p.id} 发表状态无效`);
  for (const key of ['url','pdf','code']) if ((p[key] || key === 'url') && !safeURL(p[key])) errors.push(`${p.id} 链接无效: ${key}`);
  for (const word of ['优先阅读', '本轮', 'needs supplement', 'cross_core']) if (JSON.stringify(p).includes(word)) errors.push(`${p.id} 含过程性文字: ${word}`);
}
if (errors.length) { console.error(errors.join('\n')); process.exit(1); }
console.log(`索引通过：${ids.size} 篇论文，${categories.size} 个方向，${catalogue.papers.filter(p => p.pdf).length} 个 PDF 入口。`);
