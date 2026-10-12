export const PAGE_SIZE = 12;
export const VALID_STATUS = new Set(['all', 'published', 'workshop', 'preprint', 'report']);
export const VALID_SORT = new Set(['newest', 'oldest', 'updated', 'title']);

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
  return {
    query: (params.get('q') || '').slice(0, 300),
    category: Number.isInteger(category) && category >= 1 && category <= 6 ? category : 0,
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
  if (state.period !== 'all') params.set('period', state.period);
  if (state.status !== 'all') params.set('status', state.status);
  if (state.sort !== 'newest') params.set('sort', state.sort);
  if (state.codeOnly) params.set('code', '1');
  if (state.savedOnly) params.set('saved', '1');
  if (state.page > 1) params.set('page', state.page);
  return params.toString();
}

export function searchText(paper, categories = []) {
  const names = [paper.category, ...(paper.related || [])].map(id => categories.find(c => c.id === id)?.name || '');
  return normalize([paper.title, paper.summary, paper.evidence, paper.topic, paper.venue, ...(paper.keywords || []), ...names].join(' '));
}

export function filterPapers(papers, state, { saved = new Set(), categories = [], now = new Date() } = {}) {
  const terms = normalize(state.query).split(' ').filter(Boolean);
  const cutoff = sixMonthsAgo(now);
  const today = now.toISOString().slice(0, 10);
  const result = papers.filter(paper => {
    if (state.category && paper.category !== state.category) return false;
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
    const key = state.sort === 'updated' ? 'updated' : 'date';
    const difference = dateKey(b[key]).localeCompare(dateKey(a[key]));
    return (state.sort === 'oldest' ? -difference : difference) || a.title.localeCompare(b.title, 'en');
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
  const rows = [['标题', '公开时间', '最近修订', '研究方向', '发表状态', '研究内容', '验证与边界', '论文链接', 'PDF', '代码']];
  for (const p of papers) rows.push([p.title, p.date, p.updated, categories.find(c => c.id === p.category)?.name, p.venue, p.summary, p.evidence, p.url, p.pdf, p.code]);
  return '\uFEFF' + rows.map(row => row.map(cell).join(',')).join('\r\n');
}
