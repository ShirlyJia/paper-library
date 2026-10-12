import { PAGE_SIZE, readState, stateSearch, filterPapers, safeURL, toCSV, scopePath, scopeValues, normalizeScope, paperPath, belongsTo } from './library.js?v=2';

const $ = id => document.getElementById(id);
const STORE_KEY = 'shirly-paper-library:saved:v1';
const state = readState(location.search);
let catalog, filtered = [], toastTimer;
let saved = readSaved();
const expanded = new Set();
const nodeCounts = new Map();

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

function navigate(path) {
  Object.assign(state, scopeValues(path), { page: 1 });
  for (const node of path) if (node.children) expanded.add(String(node.id));
  render({ push: true });
  setMobileDirectory(false);
  $('view-title').focus({ preventScroll: true });
  window.scrollTo({ top: 0, behavior: 'instant' });
}

function scopeLink(text, path, className) {
  const link = el('a', className, text);
  const values = scopeValues(path);
  link.dataset.scope = JSON.stringify(values);
  link.href = location.pathname + '?' + stateSearch({ ...state, ...values, page: 1 });
  link.addEventListener('click', event => {
    if (event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault(); navigate(path);
  });
  return link;
}

function setMobileDirectory(open) {
  document.querySelector('.sidebar').classList.toggle('directory-open', open);
  $('mobile-directory').setAttribute('aria-expanded', String(open));
  $('mobile-directory').lastElementChild.textContent = open ? '−' : '＋';
}

function renderCategories() {
  const list = $('categories'); list.replaceChildren();
  const all = scopeLink('', [], 'tree-link tree-all'); all.dataset.node = '0';
  all.append(el('span', '', '全部论文'), el('span', 'tree-count', catalog.papers.length));
  list.append(all);
  function build(nodes, ancestors = []) {
    const ul = el('ul', ancestors.length ? 'tree-children' : 'tree-root');
    for (const node of nodes) {
      const path = [...ancestors, node];
      const li = el('li', 'tree-item');
      const row = el('div', 'tree-row'); row.dataset.node = node.id;
      const count = catalog.papers.filter(p => belongsTo(p, node)).length;
      nodeCounts.set(String(node.id), count);
      if (node.children) {
        const toggle = el('button', 'tree-toggle', '›');
        toggle.type = 'button'; toggle.dataset.expand = node.id;
        toggle.setAttribute('aria-controls', `children-${node.id}`);
        toggle.setAttribute('aria-label', `展开或收起：${node.name}`);
        toggle.addEventListener('click', () => {
          const key = String(node.id);
          if (expanded.has(key)) expanded.delete(key); else expanded.add(key);
          updateTree();
        });
        row.append(toggle);
      } else row.append(el('span', 'tree-leaf-mark', '·'));
      const link = scopeLink('', path, 'tree-link'); link.dataset.node = node.id;
      link.title = node.description;
      link.append(el('span', 'tree-name', node.name), el('span', 'tree-count', count));
      if (!ancestors.length) link.prepend(el('span', 'tree-number', node.code));
      row.append(link); li.append(row);
      if (node.children) {
        const children = build(node.children, path); children.id = `children-${node.id}`; li.append(children);
      }
      ul.append(li);
    }
    return ul;
  }
  list.append(build(catalog.categories));
}

function updateTree() {
  const path = scopePath(catalog.categories, state);
  const current = String(path.at(-1)?.id || 0);
  const parents = new Set(path.slice(0, -1).map(n => String(n.id)));
  for (const link of document.querySelectorAll('.tree-link')) {
    const active = link.dataset.node === current;
    if (active) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
    link.classList.toggle('is-parent', parents.has(link.dataset.node));
  }
  for (const toggle of document.querySelectorAll('[data-expand]')) {
    const open = expanded.has(toggle.dataset.expand);
    toggle.setAttribute('aria-expanded', String(open));
    $(toggle.getAttribute('aria-controls')).hidden = !open;
  }
}

function renderScope() {
  const path = scopePath(catalog.categories, state);
  const current = path.at(-1);
  document.title = current ? `${current.name} — 研究书架` : '研究书架 — Shirly';
  const crumbs = $('breadcrumbs'); crumbs.replaceChildren(scopeLink('全部论文', [], 'breadcrumb-root'));
  for (let i = 0; i < path.length; i++) {
    const separator = el('span', 'breadcrumb-separator', '/'); separator.setAttribute('aria-hidden', 'true');
    const link = scopeLink(path[i].name, path.slice(0, i + 1));
    if (i === path.length - 1) link.setAttribute('aria-current', 'page');
    crumbs.append(separator, link);
  }
  $('view-level').textContent = current ? `${['研究领域', '子方向', '具体议题'][path.length - 1]}  /  ${current.code}` : 'RESEARCH LIBRARY';
  $('total-count').textContent = current ? nodeCounts.get(String(current.id)) : catalog.papers.length;
  $('count-label').textContent = current ? '本目录收录 / PAPERS' : '篇论文 / PAPERS';
  if (state.savedOnly) {
    $('view-title').textContent = '我的收藏';
    $('view-description').textContent = current ? current.description : '保存在当前浏览器中的论文。';
    $('total-count').textContent = catalog.papers.filter(p => saved.has(p.id) && (!current || belongsTo(p, current))).length;
    $('count-label').textContent = '篇收藏 / PAPERS';
  } else if (current) {
    $('view-title').textContent = current.name;
    $('view-description').textContent = current.description;
  } else {
    $('view-title').replaceChildren(document.createTextNode('结构化数据模型'), el('br'), el('span', '', '研究论文清单'));
    $('view-description').textContent = catalog.description;
  }
  const questions = $('scope-questions'); questions.replaceChildren();
  questions.hidden = path.length !== 1 || state.savedOnly || Boolean(state.query);
  if (!questions.hidden) {
    questions.append(el('span', 'questions-label', '研究问题'));
    const list = el('ul');
    for (const question of current.questions) list.append(el('li', '', question));
    questions.append(list);
  }
  const children = current ? current.children || [] : catalog.categories;
  const panel = $('directory-panel');
  panel.hidden = !children.length || Boolean(state.query) || state.savedOnly;
  const cards = $('directory-cards'); cards.replaceChildren(); cards.dataset.depth = path.length;
  if (!panel.hidden) {
    $('directory-title').textContent = ['研究领域', '子方向', '具体议题'][path.length];
    $('directory-count').textContent = `${children.length} 个${['领域', '子方向', '议题'][path.length]} · 收录总数`;
    for (const child of children) {
      const childPath = [...path, child];
      const card = el('article', 'directory-card');
      const main = el('div', 'directory-main');
      const heading = el('h3', 'directory-name');
      const link = scopeLink('', childPath, 'directory-heading');
      link.append(el('span', 'directory-code', child.code), el('span', '', child.name), el('span', 'directory-arrow', '→'));
      heading.append(link); main.append(heading, el('p', 'directory-description', child.description));
      main.append(el('span', 'directory-meta', `${nodeCounts.get(String(child.id))} 篇论文`));
      card.append(main);
      if (child.children) {
        const sublist = el('ul', 'directory-children');
        for (const next of child.children) {
          const item = el('li');
          const nextLink = scopeLink('', [...childPath, next]);
          nextLink.append(el('span', '', next.name), el('span', 'directory-child-count', nodeCounts.get(String(next.id))));
          item.append(nextLink); sublist.append(item);
        }
        card.append(sublist);
      }
      cards.append(card);
    }
  }
  $('paper-section-title').textContent = state.savedOnly ? '收藏论文' : state.query ? '检索结果' : current ? '本目录论文' : '全部论文';
  $('paper-scope-label').textContent = current ? `${current.code} / ${['领域', '子方向', '议题'][path.length - 1]}` : '';
  updateTree();
}

function createCard(paper, index) {
  const path = paperPath(paper, catalog.categories);
  const card = el('article', 'paper-card enter');
  card.dataset.id = paper.id;
  card.style.transitionDelay = `${Math.min(index % 2, 1) * 45}ms`;
  card.setAttribute('aria-labelledby', `title-${paper.id}`);
  const top = el('div', 'paper-topline');
  const tag = el('span', 'paper-code', path.at(-1).code);
  const date = el('time', 'paper-date', paper.date.replaceAll('-', '.')); date.dateTime = paper.date;
  date.title = paper.dateNote || `最早已核实公开时间：${paper.date}`;
  if (paper.updated !== paper.date) date.title += `；最近修订：${paper.updated}`;
  top.append(tag, date);
  const bookmark = el('button', 'bookmark'); bookmark.type = 'button'; bookmark.dataset.bookmark = paper.id;
  bookmark.append(bookmarkIcon()); setBookmarkLabel(bookmark, paper);
  bookmark.addEventListener('click', () => toggleSaved(paper));
  const classification = el('nav', 'paper-path'); classification.setAttribute('aria-label', '论文分类路径');
  path.forEach((node, i) => {
    if (i) { const divider = el('span', 'path-separator', '›'); divider.setAttribute('aria-hidden', 'true'); classification.append(divider); }
    classification.append(scopeLink(node.name, path.slice(0, i + 1)));
  });
  const title = el('h3', 'paper-title'); title.id = `title-${paper.id}`;
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
  card.append(top, bookmark, classification, title, summary, evidence, bottom);
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

function syncURL(push = false) {
  const search = stateSearch(state);
  const target = location.pathname + (search ? '?' + search : '');
  if (target !== location.pathname + location.search) history[push ? 'pushState' : 'replaceState'](null, '', target);
  for (const link of document.querySelectorAll('a[data-scope]')) {
    const values = JSON.parse(link.dataset.scope);
    const query = stateSearch({ ...state, ...values, page: 1 });
    link.href = location.pathname + (query ? '?' + query : '');
  }
}

function render({ push = false } = {}) {
  Object.assign(state, normalizeScope(state, catalog.categories));
  filtered = filterPapers(catalog.papers, state, { saved, categories: catalog.categories });
  state.page = Math.min(state.page, Math.max(1, Math.ceil(filtered.length / PAGE_SIZE)));
  renderScope();
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
  renderPages(filtered.length); syncURL(push);
}

function reset() { Object.assign(state, readState('')); render(); }

async function init() {
  const response = await fetch(new URL('./data/papers.json?v=2', import.meta.url), { cache: 'no-cache' });
  if (!response.ok) throw new Error(`索引读取失败 (${response.status})`);
  catalog = await response.json();
  if (!Array.isArray(catalog.papers) || !Array.isArray(catalog.categories)) throw new Error('索引格式无效');
  $('last-updated').textContent = `更新于 ${catalog.updatedAt.replaceAll('-', '.')}`;
  for (const year of [...new Set(catalog.papers.map(p => p.date.slice(0, 4)))].sort().reverse()) {
    const option = el('option', '', year); option.value = year; $('period').append(option);
  }
  if (![...$('period').options].some(o => o.value === state.period)) state.period = 'all';
  for (const node of scopePath(catalog.categories, state)) if (node.children) expanded.add(String(node.id));
  renderCategories(); render();
  $('mobile-directory').addEventListener('click', () => setMobileDirectory($('mobile-directory').getAttribute('aria-expanded') !== 'true'));
  $('collapse-tree').addEventListener('click', () => { expanded.clear(); updateTree(); });
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
  window.addEventListener('popstate', () => {
    Object.assign(state, readState(location.search));
    for (const node of scopePath(catalog.categories, state)) if (node.children) expanded.add(String(node.id));
    render();
  });
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
