export const PAGE_SIZE = 12;
export const VALID_STATUS = new Set(['all', 'published', 'workshop', 'preprint', 'report']);
export const VALID_SORT = new Set(['newest', 'oldest', 'updated', 'added', 'title']);

export function beijingDate(now = new Date()) {
  return new Date(now.getTime() + 8 * 60 * 60 * 1000).toISOString().slice(0, 10);
}

export function isFullDate(value) {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
    && !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
}

export function normalize(text = '') {
  return String(text).normalize('NFKC').toLocaleLowerCase().replace(/[–—−]/g, '-').replace(/\s+/g, ' ').trim();
}

export function dateKey(value) {
  return String(value || '').replaceAll('-', '').padEnd(8, '0');
}

export function sixMonthsAgo(now = new Date()) {
  const day = now.getUTCDate();
  const start = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - 6, 1));
  const lastDay = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 0)).getUTCDate();
  start.setUTCDate(Math.min(day, lastDay));
  return start.toISOString().slice(0, 10);
}

export function readState(search = '') {
  const params = new URLSearchParams(search);
  const category = Number(params.get('category'));
  const slug = key => /^[a-z0-9-]{1,80}$/.test(params.get(key) || '') ? params.get(key) : '';
  return {
    query: (params.get('q') || '').slice(0, 300),
    category: Number.isInteger(category) && category >= 1 && category <= 6 ? category : 0,
    section: slug('section'),
    topic: slug('topic'),
    period: /^(all|6m|\d{4})$/.test(params.get('period') || '') ? params.get('period') : 'all',
    status: VALID_STATUS.has(params.get('status')) ? params.get('status') : 'all',
    sort: VALID_SORT.has(params.get('sort')) ? params.get('sort') : 'newest',
    codeOnly: params.get('code') === '1',
    savedOnly: params.get('saved') === '1',
    page: Math.min(10000, Math.max(1, parseInt(params.get('page'), 10) || 1)),
  };
}

export function stateSearch(state) {
  const params = new URLSearchParams();
  if (state.query.trim()) params.set('q', state.query.trim());
  if (state.category) params.set('category', state.category);
  if (state.section) params.set('section', state.section);
  if (state.topic) params.set('topic', state.topic);
  if (state.period !== 'all') params.set('period', state.period);
  if (state.status !== 'all') params.set('status', state.status);
  if (state.sort !== 'newest') params.set('sort', state.sort);
  if (state.codeOnly) params.set('code', '1');
  if (state.savedOnly) params.set('saved', '1');
  if (state.page > 1) params.set('page', state.page);
  return params.toString();
}

export function scopePath(categories, state) {
  const category = categories.find(c => c.id === state.category);
  if (!category) return [];
  const section = category.children?.find(s => s.id === state.section);
  if (!section) return [category];
  const topic = section.children?.find(t => t.id === state.topic);
  return topic ? [category, section, topic] : [category, section];
}

export function scopeValues(path) {
  return { category: path[0]?.id || 0, section: path[1]?.id || '', topic: path[2]?.id || '' };
}

export function normalizeScope(state, categories) {
  return { ...state, ...scopeValues(scopePath(categories, state)) };
}

export function paperPath(paper, categories) {
  return scopePath(categories, { category: paper.category, section: paper.section, topic: paper.topicId });
}

export function belongsTo(paper, node) {
  return paper.category === node.id || paper.section === node.id || paper.topicId === node.id;
}

export function todayAdditions(catalog, { now = new Date() } = {}) {
  const date = beijingDate(now);
  const paperIds = new Set();
  const counts = new Map();
  for (const paper of catalog.papers) {
    if (paper.addedAt !== date || paperIds.has(paper.id)) continue;
    paperIds.add(paper.id);
    for (const node of paperPath(paper, catalog.categories)) {
      const key = String(node.id);
      counts.set(key, (counts.get(key) || 0) + 1);
    }
  }
  if (paperIds.size) counts.set('0', paperIds.size);
  return { date, paperIds, counts };
}

export function millisecondsUntilBeijingMidnight(now = new Date()) {
  return Date.parse(`${beijingDate(now)}T00:00:00+08:00`) + 86400000 - now.getTime();
}

export function searchText(paper, categories = []) {
  const names = [paper.category, ...(paper.related || [])].map(id => categories.find(c => c.id === id)?.name || '');
  return normalize([paper.title, ...(paper.aliases || []), paper.summary, paper.topic, paper.venue, paper.recognition?.label, ...(paper.keywords || []), ...names, ...paperPath(paper, categories).map(n => n.name)].join(' '));
}

export function filterPapers(papers, state, { saved = new Set(), categories = [], now = new Date() } = {}) {
  const terms = normalize(state.query).split(' ').filter(Boolean);
  const cutoff = sixMonthsAgo(now);
  const today = now.toISOString().slice(0, 10);
  const result = papers.filter(paper => {
    if (state.category && paper.category !== state.category) return false;
    if (state.section && paper.section !== state.section) return false;
    if (state.topic && paper.topicId !== state.topic) return false;
    if (state.status !== 'all' && paper.status !== state.status) return false;
    if (state.codeOnly && !paper.code) return false;
    if (state.savedOnly && !saved.has(paper.id)) return false;
    if (state.period === '6m' && !(paper.date.length >= 7 && paper.date >= cutoff && paper.date <= today)) return false;
    if (/^\d{4}$/.test(state.period) && !paper.date.startsWith(state.period)) return false;
    if (terms.length && !terms.every(term => searchText(paper, categories).includes(term))) return false;
    return true;
  });
  return result.sort((a, b) => {
    if (state.sort === 'title') return a.title.localeCompare(b.title, 'en');
    const key = state.sort === 'updated' ? 'updated' : state.sort === 'added' ? 'addedAt' : 'date';
    const difference = dateKey(b[key]).localeCompare(dateKey(a[key]));
    return (state.sort === 'oldest' ? -difference : difference) || a.title.localeCompare(b.title, 'en');
  });
}

export function recentCollectionUpdates(catalog, state, { now = new Date(), days = 30 } = {}) {
  const today = beijingDate(now);
  const cutoff = new Date(Date.parse(today) - (days - 1) * 86400000).toISOString().slice(0, 10);
  const path = scopePath(catalog.categories, state);
  const scope = path.at(-1);
  const papers = new Map(catalog.papers.filter(p => !scope || belongsTo(p, scope)).map(p => [p.id, p]));
  const dates = new Map();
  for (const event of catalog.collectionUpdates || []) {
    if (!isFullDate(event.date) || event.date < cutoff || event.date > today) continue;
    if (!dates.has(event.date)) dates.set(event.date, { added: new Set(), updated: new Set() });
    const day = dates.get(event.date);
    for (const kind of ['added', 'updated']) for (const id of event[kind] || []) if (papers.has(id)) day[kind].add(id);
  }
  return [...dates].sort(([a], [b]) => b.localeCompare(a)).flatMap(([date, day]) => {
    for (const id of day.added) day.updated.delete(id);
    if (!day.added.size && !day.updated.size) return [];
    const groups = new Map();
    for (const kind of ['added', 'updated']) for (const id of day[kind]) {
      const groupPath = paperPath(papers.get(id), catalog.categories).slice(0, Math.min(path.length + 1, 3));
      const node = groupPath.at(-1);
      if (!groups.has(node.id)) groups.set(node.id, { path: groupPath, added: 0, updated: 0 });
      groups.get(node.id)[kind]++;
    }
    return [{ date, added: day.added.size, updated: day.updated.size,
      groups: [...groups.values()].sort((a, b) => a.path.at(-1).code.localeCompare(b.path.at(-1).code)) }];
  });
}

export function safeURL(value) {
  try { const url = new URL(value); return url.protocol === 'https:' ? url.href : null; }
  catch { return null; }
}

export function toCSV(papers, categories) {
  const cell = value => {
    let text = String(value ?? '');
    if (/^[=+\-@\t\r]/.test(text)) text = "'" + text;
    return `"${text.replaceAll('"', '""')}"`;
  };
  const rows = [['标题', '公开时间', '本站收录', '最近修订', '研究领域', '子方向', '具体议题', '发表与收录', '会议标记', '标记来源', '研究内容', '论文链接', 'PDF', '代码']];
  for (const p of papers) {
    const path = paperPath(p, categories);
    rows.push([p.title, p.date, p.addedAt, p.updated, ...[0,1,2].map(i => path[i]?.name || ''), p.venue, p.recognition?.label, p.recognition?.source, p.summary, p.url, p.pdf, p.code]);
  }
  return '\uFEFF' + rows.map(row => row.map(cell).join(',')).join('\r\n');
}
