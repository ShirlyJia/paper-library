import { PAGE_SIZE, readState, stateSearch, filterPapers, safeURL, toCSV, scopePath, scopeValues, normalizeScope, paperPath, belongsTo, recentCollectionUpdates, beijingDate, todayAdditions, millisecondsUntilBeijingMidnight, defaultSort, searchTerms, highlightParts } from './library.js?v=11';

const $ = id => document.getElementById(id);
const STORE_KEY = 'structured-data-paper-library:saved:v1';
// Only used to migrate existing browser bookmarks; never displayed on the site.
const LEGACY_STORE_KEY = 'shirly-paper-library:saved:v1';
const state = readState(location.search);
let catalog, filtered = [], toastTimer, today, dayTimer, terms = [];
let saved = readSaved();
const expanded = new Set();
const nodeCounts = new Map();
const catalogChanges = new Map();

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function readSaved() {
  try {
    const stored = localStorage.getItem(STORE_KEY);
    const legacy = stored === null ? localStorage.getItem(LEGACY_STORE_KEY) : null;
    const value = JSON.parse(stored ?? legacy ?? '[]');
    if (stored === null && legacy !== null && Array.isArray(value)) {
      try {
        localStorage.setItem(STORE_KEY, JSON.stringify(value));
        localStorage.removeItem(LEGACY_STORE_KEY);
      } catch { /* Keep the legacy copy if storage is unavailable. */ }
    }
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

function highlighted(node, text) {
  node.replaceChildren(...highlightParts(text, terms).map(part => part.hit ? el('mark', '', part.text) : part.text));
  return node;
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

function appendTodayCount(parent, nodeId) {
  const count = today.counts.get(String(nodeId));
  if (!count) return;
  const badge = el('span', 'today-count', `+${count}`);
  badge.title = `今日新收录 ${count} 篇 · 北京时间`;
  badge.setAttribute('aria-label', badge.title);
  parent.append(badge);
}

function directoryCounts(count, nodeId, className) {
  const counts = el('span', 'directory-counts');
  appendTodayCount(counts, nodeId);
  counts.append(el('span', className, count));
  return counts;
}

function renderCategories() {
  const list = $('categories'); list.replaceChildren();
  const all = scopeLink('', [], 'tree-link tree-all'); all.dataset.node = '0';
  all.append(el('span', 'tree-name', '全部论文'), directoryCounts(catalog.papers.length, '0', 'tree-count'));
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
      link.append(el('span', 'tree-name', node.name), directoryCounts(count, node.id, 'tree-count'));
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
  document.title = current ? `${current.name} — ${catalog.title}` : catalog.title;
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
    $('view-title').textContent = '本机收藏';
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
      main.append(directoryCounts(`${nodeCounts.get(String(child.id))} 篇论文`, child.id, 'directory-meta'));
      card.append(main);
      if (child.children) {
        const sublist = el('ul', 'directory-children');
        for (const next of child.children) {
          const item = el('li');
          const nextLink = scopeLink('', [...childPath, next]);
          nextLink.append(el('span', '', next.name), directoryCounts(nodeCounts.get(String(next.id)), next.id, 'directory-child-count'));
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

function activityCount(added, updated) {
  return [added ? `新增 ${added} 篇` : '', updated ? `资料更新 ${updated} 次` : ''].filter(Boolean).join(' · ');
}

function renderActivity() {
  const days = recentCollectionUpdates(catalog, state);
  const path = scopePath(catalog.categories, state);
  const scopeName = path.at(-1)?.name || '全站';
  const added = days.reduce((n, day) => n + day.added, 0);
  const updated = days.reduce((n, day) => n + day.updated, 0);
  $('activity-summary').textContent = `${path.length ? '本目录' : '全站'}近 30 天 · ${days.length ? `${days.length} 个更新日 · ${activityCount(added, updated)}` : '暂无更新'}`;
  $('activity-note').textContent = `${scopeName}的收录与资料维护记录，按当前目录汇总；与论文发表、修订时间分别记录。`;
  const list = $('activity-days'); list.replaceChildren();
  for (const day of days) {
    const section = el('section', 'activity-day');
    const heading = el('h3', 'activity-day-heading');
    const date = el('time', '', day.date.replaceAll('-', '.')); date.dateTime = day.date;
    heading.append(date, el('span', '', activityCount(day.added, day.updated)));
    const groups = el('ul', 'activity-groups');
    for (const group of day.groups) {
      const node = group.path.at(-1);
      const item = el('li');
      const link = el('a', 'activity-link', node.name);
      const next = { ...readState(), ...scopeValues(group.path), sort: 'added' };
      link.href = location.pathname + '?' + stateSearch(next);
      link.title = '查看该方向全部论文，按最近收录排序';
      link.addEventListener('click', event => {
        if (event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault(); Object.assign(state, next); navigate(group.path);
      });
      item.append(link, el('span', 'activity-count', activityCount(group.added, group.updated)));
      groups.append(item);
    }
    section.append(heading, groups); list.append(section);
  }
  if (!days.length) list.append(el('p', 'activity-empty', '近 30 天没有新增或资料更新，已有论文仍可正常浏览。'));
  $('activity-board').hidden = false;
}

function createCard(paper) {
  const path = paperPath(paper, catalog.categories);
  const card = el('article', 'paper-card');
  const isNewToday = today.paperIds.has(paper.id);
  card.classList.toggle('is-new-today', isNewToday);
  card.dataset.id = paper.id;
  card.setAttribute('aria-labelledby', `title-${paper.id}`);
  const top = el('div', 'paper-topline');
  const tag = el('span', 'paper-reference');
  tag.append(el('span', 'paper-code', path.at(-1).code));
  if (isNewToday) {
    const label = el('span', 'paper-new-label', '今日收录');
    label.title = `今日加入本站（北京时间 ${today.date}）`;
    tag.append(label);
  }
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
  title.append(highlighted(externalLink('', paper.url), paper.title));
  const publication = el('div', 'paper-publication');
  publication.setAttribute('aria-label', '发表与会议标记');
  const published = ['published', 'workshop'].includes(paper.status);
  const venue = el('span', 'venue-badge', `${published ? '已收录 · ' : ''}${paper.venue}`);
  venue.dataset.status = paper.status;
  publication.append(venue);
  if (paper.recognition && safeURL(paper.recognition.source)) {
    const recognition = externalLink(paper.recognition.label, paper.recognition.source, 'recognition-badge');
    recognition.title = `${paper.venue} · ${paper.recognition.label}；查看来源`;
    recognition.setAttribute('aria-label', `${paper.recognition.label}：查看 ${paper.title} 的会议标记来源`);
    publication.append(recognition);
  }
  const summary = highlighted(el('p', 'paper-summary'), paper.summary);
  const bottom = el('div', 'paper-bottom');
  const collected = el('span', 'paper-collected', '本站收录 ');
  const addedAt = el('time', '', paper.addedAt.replaceAll('-', '.')); addedAt.dateTime = paper.addedAt;
  collected.append(addedAt);
  collected.title = `加入本站的日期：${paper.addedAt}；不代表论文发表日期。${catalogChanges.has(paper.id) ? `本站资料最近更新：${catalogChanges.get(paper.id)}。` : ''}`;
  const links = el('div', 'paper-links');
  if (safeURL(paper.code)) links.append(externalLink('代码 ↗', paper.code));
  if (safeURL(paper.pdf)) {
    const pdf = externalLink('PDF ↓', paper.pdf);
    pdf.setAttribute('aria-label', `打开或下载 PDF：${paper.title}`);
    pdf.title = '打开 PDF，可使用阅读器下载';
    links.append(pdf);
  }
  links.append(externalLink('原文 ↗', paper.url));
  bottom.append(collected, links);
  card.append(top, bookmark, classification, title, publication, summary, bottom);
  card.addEventListener('click', event => {
    if (event.target.closest('a,button') || getSelection()?.toString()) return;
    window.open(safeURL(paper.url), '_blank', 'noopener,noreferrer');
  });
  return card;
}

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
  const now = new Date();
  if (today?.date !== beijingDate(now)) {
    today = todayAdditions(catalog, { now });
    renderCategories();
  }
  Object.assign(state, normalizeScope(state, catalog.categories));
  terms = searchTerms(state.query);
  document.body.classList.toggle('is-searching', terms.length > 0);
  filtered = filterPapers(catalog.papers, state, { saved, categories: catalog.categories });
  state.page = Math.min(state.page, Math.max(1, Math.ceil(filtered.length / PAGE_SIZE)));
  renderScope();
  renderActivity();
  $('period').value = state.period; $('status').value = state.status; $('sort').value = state.sort; $('code-only').checked = state.codeOnly;
  if ($('search').value !== state.query) $('search').value = state.query;
  updateSavedCount();
  const start = (state.page - 1) * PAGE_SIZE;
  $('papers').replaceChildren(...filtered.slice(start, start + PAGE_SIZE).map(createCard));
  $('papers').setAttribute('aria-busy', 'false');
  $('result-count').replaceChildren(el('strong', '', String(filtered.length)), document.createTextNode(` 篇论文${filtered.length ? `  /  显示 ${start + 1}–${Math.min(start + PAGE_SIZE, filtered.length)}` : ''}`));
  $('empty-state').hidden = filtered.length > 0;
  const scope = scopePath(catalog.categories, state).at(-1);
  const emptyScope = scope && !catalog.papers.some(paper => belongsTo(paper, scope));
  $('empty-description').textContent = state.savedOnly ? '点击论文右上角的书签图标，将它加入收藏。' : emptyScope ? '此方向尚无已核验论文，后续审核通过后收录。' : '换一个关键词，或放宽筛选条件。';
  $('reset').hidden = !state.query && !state.category && state.period === 'all' && state.status === 'all' && !state.codeOnly && !state.savedOnly;
  $('export-csv').disabled = !filtered.length;
  renderPages(filtered.length); syncURL(push);
}

function reset() { Object.assign(state, readState('')); render(); }

function refreshDay() {
  if (today.date !== beijingDate()) render();
  clearTimeout(dayTimer);
  dayTimer = setTimeout(refreshDay, millisecondsUntilBeijingMidnight() + 50);
}

async function init() {
  const response = await fetch(new URL('./data/papers.json', import.meta.url), { cache: 'no-cache' });
  if (!response.ok) throw new Error(`索引读取失败 (${response.status})`);
  catalog = await response.json();
  if (!Array.isArray(catalog.papers) || !Array.isArray(catalog.categories)) throw new Error('索引格式无效');
  for (const event of catalog.collectionUpdates || []) for (const id of event.updated) {
    if (!catalogChanges.has(id) || event.date > catalogChanges.get(id)) catalogChanges.set(id, event.date);
  }
  $('last-updated').textContent = `更新于 ${catalog.updatedAt.replaceAll('-', '.')}`;
  for (const year of [...new Set(catalog.papers.map(p => p.date.slice(0, 4)))].sort().reverse()) {
    const option = el('option', '', year); option.value = year; $('period').append(option);
  }
  if (![...$('period').options].some(o => o.value === state.period)) state.period = 'all';
  for (const node of scopePath(catalog.categories, state)) if (node.children) expanded.add(String(node.id));
  render();
  refreshDay();
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshDay(); });
  window.addEventListener('focus', refreshDay);
  window.addEventListener('pageshow', refreshDay);
  $('mobile-directory').addEventListener('click', () => setMobileDirectory($('mobile-directory').getAttribute('aria-expanded') !== 'true'));
  $('collapse-tree').addEventListener('click', () => { expanded.clear(); updateTree(); });
  let searchTimer;
  $('search').addEventListener('input', event => {
    const value = event.target.value;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      if (state.sort === defaultSort(state.query)) state.sort = defaultSort(value);
      Object.assign(state, { query: value, page: 1 }); render();
    }, 110);
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
