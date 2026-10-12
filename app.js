import { PAGE_SIZE, readState, stateSearch, filterPapers, safeURL, toCSV } from './library.js';

const $ = id => document.getElementById(id);
const STORE_KEY = 'shirly-paper-library:saved:v1';
const state = readState(location.search);
let catalog, filtered = [], toastTimer;
let saved = readSaved();

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function readSaved() {
  try {
    const value = JSON.parse(localStorage.getItem(STORE_KEY) || '[]');
    return new Set(Array.isArray(value) ? value.filter(v => typeof v === 'string') : []);
  } catch { return new Set(); }
}

function toast(message) {
  $('toast').textContent = message;
  $('toast').classList.add('active');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('toast').classList.remove('active'), 2400);
}

function bookmarkIcon() {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('width', '16'); svg.setAttribute('height', '18');
  svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS(svg.namespaceURI, 'path');
  for (const [key, value] of Object.entries({ d: 'M6 3h12v18l-6-4-6 4V3Z', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.6', 'stroke-linejoin': 'round' })) path.setAttribute(key, value);
  svg.append(path); return svg;
}

function externalLink(text, url, className) {
  const link = el('a', className, text);
  link.href = safeURL(url);
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  return link;
}

function toggleSaved(paper) {
  if (saved.has(paper.id)) saved.delete(paper.id); else saved.add(paper.id);
  try { localStorage.setItem(STORE_KEY, JSON.stringify([...saved])); }
  catch { toast('浏览器未允许保存；本次浏览内仍可收藏。'); }
  if (state.savedOnly) render();
  else {
    const button = document.querySelector(`[data-bookmark="${CSS.escape(paper.id)}"]`);
    if (button) setBookmarkLabel(button, paper);
    updateSavedCount();
  }
}

function setBookmarkLabel(button, paper) {
  const active = saved.has(paper.id);
  button.setAttribute('aria-pressed', String(active));
  button.setAttribute('aria-label', `${active ? '取消收藏' : '收藏'}：${paper.title}`);
  button.title = active ? '取消收藏' : '收藏到此浏览器';
}

function updateSavedCount() {
  $('saved-count').textContent = catalog.papers.filter(p => saved.has(p.id)).length;
  $('saved-toggle').setAttribute('aria-pressed', String(state.savedOnly));
}

function renderCategories() {
  const list = $('categories'); list.replaceChildren();
  for (const category of [{ id: 0, name: '全部论文' }, ...catalog.categories]) {
    const count = category.id ? catalog.papers.filter(p => p.category === category.id).length : catalog.papers.length;
    const button = el('button', 'category-button');
    button.type = 'button'; button.dataset.category = category.id;
    button.setAttribute('aria-pressed', String(category.id === state.category));
    button.append(el('span', 'category-number', category.id ? String(category.id).padStart(2, '0') : '—'), el('span', 'category-name', category.name), el('span', 'category-count', count));
    button.addEventListener('click', () => {
      state.category = category.id; state.page = 1; render();
      if (matchMedia('(max-width: 700px)').matches) button.scrollIntoView({ inline: 'center', block: 'nearest' });
    });
    list.append(button);
  }
}

function createCard(paper, index) {
  const category = catalog.categories.find(c => c.id === paper.category);
  const card = el('article', 'paper-card enter');
  card.dataset.id = paper.id;
  card.style.transitionDelay = `${Math.min(index % 2, 1) * 45}ms`;
  card.setAttribute('aria-labelledby', `title-${paper.id}`);
  const top = el('div', 'paper-topline');
  const tag = el('span', 'category-tag', category.name); tag.dataset.category = category.id;
  const date = el('time', 'paper-date', paper.date.replaceAll('-', '.')); date.dateTime = paper.date;
  date.title = paper.dateNote || `最早已核实公开时间：${paper.date}`;
  if (paper.updated !== paper.date) date.title += `；最近修订：${paper.updated}`;
  top.append(tag, date);
  const bookmark = el('button', 'bookmark'); bookmark.type = 'button'; bookmark.dataset.bookmark = paper.id;
  bookmark.append(bookmarkIcon()); setBookmarkLabel(bookmark, paper);
  bookmark.addEventListener('click', () => toggleSaved(paper));
  const title = el('h2', 'paper-title'); title.id = `title-${paper.id}`;
  title.append(externalLink(paper.title, paper.url));
  const summary = el('p', 'paper-summary', paper.summary);
  const evidence = el('p', 'paper-evidence');
  evidence.append(el('span', '', '验证与边界'), document.createTextNode(paper.evidence));
  const bottom = el('div', 'paper-bottom');
  const venue = el('span', 'venue', paper.venue); venue.dataset.status = paper.status;
  const links = el('div', 'paper-links');
  if (safeURL(paper.code)) links.append(externalLink('代码 ↗', paper.code));
  if (safeURL(paper.pdf)) {
    const pdf = externalLink('PDF ↓', paper.pdf);
    pdf.setAttribute('aria-label', `打开或下载 PDF：${paper.title}`);
    pdf.title = '打开 PDF，可使用阅读器下载';
    links.append(pdf);
  }
  links.append(externalLink('原文 ↗', paper.url));
  bottom.append(venue, links);
  card.append(top, bookmark, title, summary, evidence, bottom);
  card.addEventListener('click', event => {
    if (event.target.closest('a,button') || getSelection()?.toString()) return;
    window.open(safeURL(paper.url), '_blank', 'noopener,noreferrer');
  });
  return card;
}

const observer = new IntersectionObserver(entries => {
  for (const entry of entries) if (entry.isIntersecting) {
    entry.target.classList.add('visible'); observer.unobserve(entry.target);
  }
}, { rootMargin: '100px' });

function renderPages(total) {
  const nav = $('pagination'); nav.replaceChildren();
  const pages = Math.ceil(total / PAGE_SIZE);
  if (pages <= 1) return;
  const addButton = (text, page, disabled = false, arrow = false) => {
    const button = el('button', arrow ? 'page-arrow' : '', text);
    button.disabled = disabled; button.type = 'button';
    if (!arrow) button.setAttribute('aria-label', `第 ${page} 页`);
    if (page === state.page && !arrow) button.setAttribute('aria-current', 'page');
    button.addEventListener('click', () => {
      state.page = page; render();
      $('result-count').scrollIntoView({ block: 'start', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
    });
    nav.append(button);
  };
  addButton('← 上一页', state.page - 1, state.page === 1, true);
  const visible = new Set([1, pages, state.page - 1, state.page, state.page + 1]);
  if (pages <= 8) for (let i = 1; i <= pages; i++) visible.add(i);
  let previous = 0;
  for (const page of [...visible].filter(n => n >= 1 && n <= pages).sort((a,b) => a-b)) {
    if (page - previous > 1) nav.append(el('span', 'page-gap', '…'));
    addButton(String(page).padStart(2, '0'), page); previous = page;
  }
  addButton('下一页 →', state.page + 1, state.page === pages, true);
}

function syncURL() {
  const search = stateSearch(state);
  const target = location.pathname + (search ? '?' + search : '');
  if (target !== location.pathname + location.search) history.replaceState(null, '', target);
}

function render() {
  filtered = filterPapers(catalog.papers, state, { saved, categories: catalog.categories });
  state.page = Math.min(state.page, Math.max(1, Math.ceil(filtered.length / PAGE_SIZE)));
  const category = catalog.categories.find(c => c.id === state.category);
  if (state.savedOnly) {
    $('view-title').textContent = '我的收藏';
    $('view-description').textContent = '保存在当前浏览器中的论文。';
  } else if (category) {
    $('view-title').textContent = category.name;
    $('view-description').textContent = category.description;
  } else {
    $('view-title').replaceChildren(document.createTextNode('结构化智能'), el('br'), el('span', '', '论文索引'));
    $('view-description').textContent = catalog.description;
  }
  for (const button of document.querySelectorAll('.category-button')) button.setAttribute('aria-pressed', String(Number(button.dataset.category) === state.category));
  $('period').value = state.period; $('status').value = state.status; $('sort').value = state.sort; $('code-only').checked = state.codeOnly;
  if ($('search').value !== state.query) $('search').value = state.query;
  updateSavedCount();
  const start = (state.page - 1) * PAGE_SIZE;
  const list = $('papers'); observer.disconnect(); list.replaceChildren();
  for (const [index, paper] of filtered.slice(start, start + PAGE_SIZE).entries()) {
    const card = createCard(paper, index); list.append(card); observer.observe(card);
  }
  list.setAttribute('aria-busy', 'false');
  $('result-count').replaceChildren(el('strong', '', String(filtered.length)), document.createTextNode(` 篇论文${filtered.length ? `  /  显示 ${start + 1}–${Math.min(start + PAGE_SIZE, filtered.length)}` : ''}`));
  $('empty-state').hidden = filtered.length > 0;
  $('empty-description').textContent = state.savedOnly ? '点击论文右上角的书签图标，将它加入收藏。' : '换一个关键词，或放宽筛选条件。';
  $('reset').hidden = !state.query && !state.category && state.period === 'all' && state.status === 'all' && !state.codeOnly && !state.savedOnly;
  $('export-csv').disabled = !filtered.length;
  renderPages(filtered.length); syncURL();
}

function reset() { Object.assign(state, readState('')); render(); }

async function init() {
  const response = await fetch(new URL('./data/papers.json', import.meta.url), { cache: 'no-cache' });
  if (!response.ok) throw new Error(`索引读取失败 (${response.status})`);
  catalog = await response.json();
  if (!Array.isArray(catalog.papers) || !Array.isArray(catalog.categories)) throw new Error('索引格式无效');
  $('total-count').textContent = catalog.papers.length;
  $('last-updated').textContent = `更新于 ${catalog.updatedAt.replaceAll('-', '.')}`;
  for (const year of [...new Set(catalog.papers.map(p => p.date.slice(0, 4)))].sort().reverse()) {
    const option = el('option', '', year); option.value = year; $('period').append(option);
  }
  if (![...$('period').options].some(o => o.value === state.period)) state.period = 'all';
  renderCategories(); render();
  let searchTimer;
  $('search').addEventListener('input', event => {
    const value = event.target.value;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { state.query = value; state.page = 1; render(); }, 110);
  });
  for (const [id, key] of [['period', 'period'], ['status', 'status'], ['sort', 'sort'], ['code-only', 'codeOnly']]) {
    $(id).addEventListener('change', event => { state[key] = id === 'code-only' ? event.target.checked : event.target.value; state.page = 1; render(); });
  }
  $('saved-toggle').addEventListener('click', () => { state.savedOnly = !state.savedOnly; state.page = 1; render(); });
  $('reset').addEventListener('click', reset); $('empty-reset').addEventListener('click', reset);
  $('export-csv').addEventListener('click', () => {
    const blob = new Blob([toCSV(filtered, catalog.categories)], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob); const link = el('a');
    link.href = url; link.download = `paper-library-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    toast(`已导出 ${filtered.length} 篇论文`);
  });
  window.addEventListener('popstate', () => { Object.assign(state, readState(location.search)); render(); });
  window.addEventListener('storage', event => { if (event.key === STORE_KEY) { saved = readSaved(); render(); } });
  document.addEventListener('keydown', event => {
    if (event.key === '/' && !event.ctrlKey && !event.metaKey && !['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)) {
      event.preventDefault(); $('search').focus();
    }
    if (event.key === 'Escape' && document.activeElement === $('search')) $('search').blur();
  });
}

init().catch(error => {
  $('papers').setAttribute('aria-busy', 'false');
  $('result-count').textContent = '索引暂时无法加载';
  $('empty-state').hidden = false;
  $('empty-state').querySelector('h2').textContent = '请重新载入书架';
  $('empty-description').textContent = '连接恢复后即可继续浏览。';
  $('empty-reset').textContent = '重新加载';
  $('empty-reset').addEventListener('click', () => location.reload());
  console.error(error);
});
