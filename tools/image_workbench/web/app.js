'use strict';

const app = {
  data: null,
  tab: 'deliver',
  selected: new Set(),
  draftSelected: {},
  overrides: {},
  slider: {},
  openDetails: new Set(),
  onlyUnadopted: false,
  instructions: {},
  timer: null,
  busy: false,
  // Review workspace state. The viewer is built once per image and updated in place,
  // so polling and resizing cannot replace it while the user is dragging.
  processedId: null,
  processedListSig: '',
  viewerItemId: null,
  viewerVersionSig: '',
  view: null,
  interacting: false,
  pendingState: null,
  activeDraftId: null,
  draftListSig: '',
  draftPreviewId: null,
  draftPreviewStatus: '',
  draftPreviewSig: '',
  historyOpen: false,
  draftExpanded: false,
  resizeFrame: 0,
};

const STATUS_LABELS = {
  received: '已接收', previewed: '待处理', planned: '待开始',
  waiting_ai: '等 AI 回传', processing_local: '本机处理中',
  processed: '已处理', failed: '失败', cancelled: '已取消',
  adopted: '已采用', draft: '已入库', enabled: '已启用', archived: '已归档',
};
const TIME_LABELS = { day: '白天', dusk: '黄昏', night: '夜晚', any: '不分时段' };
const PLACEHOLDER_IMAGE = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
}

function bytes(value) {
  if (!value && value !== 0) return '—';
  const units = ['B', 'KB', 'MB', 'GB'];
  let number = Number(value), index = 0;
  while (number >= 1024 && index < units.length - 1) { number /= 1024; index += 1; }
  return `${number.toFixed(index ? 1 : 0)} ${units[index]}`;
}

function tag(text, kind = '') {
  return `<span class="tag ${kind}">${esc(text)}</span>`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const text = await response.text();
  let data = {};
  try { data = text ? JSON.parse(text) : {}; } catch { data = { error: text }; }
  if (!response.ok) {
    const error = new Error(data.error || `HTTP ${response.status}`);
    error.payload = data;
    throw error;
  }
  return data;
}

async function fetchText(path) {
  const response = await fetch(path);
  const text = await response.text();
  if (!response.ok) throw new Error(text || `HTTP ${response.status}`);
  return text;
}

function toast(message, error = false) {
  const element = document.getElementById('toast');
  element.textContent = message;
  element.classList.toggle('error', error);
  element.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { element.hidden = true; }, 4200);
}

function itemById(id) {
  return (app.data?.items || []).find((item) => item.id === id);
}

function taskById(id) {
  return (app.data?.tasks || []).find((task) => task.taskId === id);
}

function draftById(id) {
  return (app.data?.drafts || []).find((draft) => draft.draftId === id);
}

function versionUrl(version) {
  return `/media/${version.path}`;
}

function settingsHtml(settings, disabled = false) {
  const value = (name, fallback) => settings && settings[name] !== undefined ? settings[name] : fallback;
  return `
    <label>降噪 <input type="range" name="denoise" min="0" max="1" step="0.05" value="${esc(value('denoise', 0.35))}" ${disabled ? 'disabled' : ''}><output>${Math.round(value('denoise', 0.35) * 100)}%</output></label>
    <label>调色 <input type="range" name="color" min="0" max="1" step="0.05" value="${esc(value('color', 0.4))}" ${disabled ? 'disabled' : ''}><output>${Math.round(value('color', 0.4) * 100)}%</output></label>
    <label>放大 <select name="upscale" ${disabled ? 'disabled' : ''}>
      <option value="auto" ${value('upscale', 'auto') === 'auto' ? 'selected' : ''}>尺寸不足时本机放大</option>
      <option value="never" ${value('upscale', 'auto') === 'never' ? 'selected' : ''}>不放大</option>
    </select></label>
    <label>去字 <select name="removeText" ${disabled ? 'disabled' : ''}>
      <option value="auto" ${value('removeText', 'auto') === 'auto' ? 'selected' : ''}>需要时生成 AI 任务</option>
      <option value="never" ${value('removeText', 'auto') === 'never' ? 'selected' : ''}>不去字</option>
    </select></label>
    <label class="check"><input type="checkbox" name="trimBorders" ${value('trimBorders', true) ? 'checked' : ''} ${disabled ? 'disabled' : ''}> 去除非画面白边</label>
    <label class="check"><input type="checkbox" name="preserveSignature" ${value('preserveSignature', true) ? 'checked' : ''} ${disabled ? 'disabled' : ''}> 保留画师签名</label>`;
}

function readSettings(root) {
  const result = {};
  root.querySelectorAll('[name]').forEach((element) => {
    if (element.type === 'checkbox') result[element.name] = element.checked;
    else if (element.type === 'range') result[element.name] = Number(element.value);
    else result[element.name] = element.value;
  });
  return result;
}

function batchSettings() {
  return readSettings(document.getElementById('batch-settings'));
}

function analysisHtml(item) {
  const analysis = item.analysis;
  if (!analysis) return '<p class="card-note">还没有分析；开始后先预览再处理。</p>';
  const borders = analysis.borders || {};
  const text = analysis.text || {};
  const time = analysis.time || {};
  const quality = analysis.quality || {};
  return `<div class="analysis">
    <div><b>尺寸</b> <span>${analysis.width} × ${analysis.height}</span></div>
    <div><b>非画面边缘</b> <span>${borders.detected ? `检出 ${Math.round((borders.confidence || 0) * 100)}%${borders.auto === false ? ' · 需确认' : ''}` : '未检出'}</span></div>
    <div><b>文字</b> <span>${text.needed ? `需要 · ${Math.round((text.confidence || 0) * 100)}%` : '不需要'}</span></div>
    <div><b>签名风险</b> <span>${text.signatureRisk ? '底部疑似签名' : '未标出'}</span></div>
    <div><b>放大</b> <span>${analysis.upscale?.needed ? '建议本机放大' : '尺寸足够'}</span></div>
    <div><b>时段建议</b> <span>${TIME_LABELS[time.suggestion] || '不分时段'} · ${Math.round((time.confidence || 0) * 100)}%</span></div>
    <div><b>清晰度</b> <span>${Math.round((quality.sharpness || 0) * 100)}%</span></div>
    <div><b>噪点</b> <span>${Math.round((quality.noise || 0) * 100)}%</span></div>
  </div>${(analysis.uncertainties || []).length ? `<p class="card-note error">需要确认：${analysis.uncertainties.map((entry) => esc(entry.reason || entry.kind)).join('；')}</p>` : ''}`;
}

function itemMeta(item) {
  return `<div class="card-meta">
    ${tag(STATUS_LABELS[item.status] || item.status, item.status === 'failed' ? 'warn' : item.status === 'processed' || item.status === 'adopted' ? 'ok' : '')}
    ${tag(item.original.format || '?')}
    ${tag(`${item.original.size[0]} × ${item.original.size[1]}`)}
    ${tag(bytes(item.original.bytes))}
    ${item.duplicateOf ? tag(`重复于 ${item.duplicateOf}`) : ''}
    ${item.time ? tag(TIME_LABELS[item.time] || item.time, 'blue') : ''}
  </div>`;
}

function itemHead(item) {
  return `<div class="card-head"><h3>${esc(item.filename || item.id)}</h3><span class="id">${esc(item.id)}</span></div>`;
}

function itemSettings(item) {
  const override = app.overrides[item.id];
  return `<details class="timeline" data-key="settings-${item.id}">
    <summary>单张覆盖设置${override ? ' · 已覆盖' : ''}</summary>
    <div class="settings" data-settings-for="${item.id}">
      ${settingsHtml(override || item.settings || {})}
      <div class="actions">
        <button type="button" data-action="save-settings" data-id="${item.id}">保存单张设置</button>
        <button type="button" class="ghost" data-action="clear-settings" data-id="${item.id}">清除覆盖</button>
      </div>
    </div>
  </details>`;
}

function itemCard(item, options = {}) {
  const selectable = options.selectable !== false;
  const checked = (options.checked ? 'checked' : '');
  const actions = options.actions || '';
  return `<article class="card ${app.selected.has(item.id) ? 'selected' : ''}" data-item="${item.id}">
    <img class="card-thumb" src="${esc(item.thumbUrl)}" alt="${esc(item.filename || item.id)} 的缩略图" loading="lazy">
    <div class="card-main">
      ${itemHead(item)}
      ${itemMeta(item)}
      ${analysisHtml(item)}
      ${options.error || ''}
      ${selectable ? `<label class="check"><input type="checkbox" data-select="${item.id}" ${checked}> 选择这张</label>` : ''}
      ${options.timeline || ''}
      ${itemSettings(item)}
      <div class="card-actions">${actions}</div>
    </div>
  </article>`;
}

function empty(text) {
  return `<div class="empty">${esc(text)}</div>`;
}

function renderDeliver() {
  const items = (app.data?.items || []).filter((item) => ['received', 'previewed'].includes(item.status));
  const list = document.getElementById('delivered-list');
  if (!items.length) { list.innerHTML = empty('还没有投递。把图片拖进来，或放进接收文件夹。'); return; }
  list.innerHTML = items.map((item) => itemCard(item, {
    checked: app.selected.has(item.id),
    actions: `<button type="button" class="primary" data-action="start" data-id="${item.id}">开始处理</button>`,
  })).join('');
}

function renderPending() {
  const items = (app.data?.items || []).filter((item) =>
    ['received', 'previewed', 'planned', 'waiting_ai', 'processing_local', 'failed', 'cancelled'].includes(item.status));
  const list = document.getElementById('pending-list');
  if (!items.length) { list.innerHTML = empty('没有待处理的图片。'); return; }
  list.innerHTML = items.map((item) => {
    const actions = [];
    if (['received', 'previewed', 'planned', 'failed', 'cancelled'].includes(item.status)) {
      actions.push(`<button type="button" class="primary" data-action="start" data-id="${item.id}">开始</button>`);
    }
    if (item.status === 'processing_local') {
      actions.push(`<button type="button" data-action="cancel" data-id="${item.id}">取消未开始步骤</button>`);
    }
    if (['failed', 'cancelled'].includes(item.status)) {
      actions.push(`<button type="button" data-action="retry" data-id="${item.id}">从失败步骤重试</button>`);
    }
    const timeChoice = item.timeChoice || 'auto';
    actions.push(`<select data-time-for="${item.id}" aria-label="时段">
      <option value="auto" ${timeChoice === 'auto' ? 'selected' : ''}>自动（按分析）</option>
      <option value="day" ${timeChoice === 'day' ? 'selected' : ''}>白天</option>
      <option value="dusk" ${timeChoice === 'dusk' ? 'selected' : ''}>黄昏</option>
      <option value="night" ${timeChoice === 'night' ? 'selected' : ''}>夜晚</option>
      <option value="any" ${timeChoice === 'any' ? 'selected' : ''}>不分时段</option>
    </select>`);
    const error = item.error ? `<p class="card-note error">${esc(item.error.message || item.error)}</p>` : '';
    return itemCard(item, {
      checked: app.selected.has(item.id), error,
      actions: actions.join(''),
    });
  }).join('');
}

function renderAI() {
  const tasks = app.data?.tasks || [];
  const list = document.getElementById('ai-list');
  if (!tasks.length) { list.innerHTML = empty('还没有 AI 任务。去字判断需要时，这里会出现任务。'); return; }
  list.innerHTML = tasks.map((task) => {
    const item = itemById(task.itemId);
    const status = task.status;
    const instruction = app.instructions[task.taskId];
    const actions = [];
    if (status === 'waiting') {
      actions.push(`<button type="button" class="primary" data-action="copy-instruction" data-task="${task.taskId}">复制指令</button>`);
      if (task.needsConfirmation) {
        actions.push(`<button type="button" data-action="confirm-task" data-task="${task.taskId}">确认并继续</button>`);
      }
      actions.push(`<button type="button" data-action="recreate-task" data-task="${task.taskId}">重新生成任务</button>`);
    }
    if (['rejected', 'late', 'conflict', 'superseded'].includes(status)) {
      actions.push(`<button type="button" data-action="recreate-task" data-task="${task.taskId}">重新生成任务</button>`);
    }
    if (instruction) {
      actions.push(`<pre class="instruction">${esc(instruction)}</pre>`);
    }
    return `<article class="card" data-task="${task.taskId}">
      <img class="card-thumb" src="${esc(item ? item.thumbUrl : '')}" alt="" loading="lazy">
      <div class="card-main">
        <div class="card-head"><h3>${esc(task.taskId)}</h3><span class="id">${esc(task.itemId)}</span></div>
        <div class="card-meta">
          ${tag(status, ['rejected', 'late', 'conflict'].includes(status) ? 'warn' : status === 'done' ? 'ok' : 'blue')}
          ${task.needsConfirmation ? tag('需要确认', 'warn') : ''}
          ${tag(`置信 ${Math.round((task.confidence || 0) * 100)}%`)}
          ${tag(`版本 v${task.version}`)}
        </div>
        ${task.error ? `<p class="card-note error">${esc(task.error)}</p>` : ''}
        ${task.note && task.note !== task.error ? `<p class="card-note">${esc(task.note)}</p>` : ''}
        <p class="card-note">输入 ${esc(task.input?.sha256?.slice(0, 16) || '')}… · 结果写到 <code>${esc(task.jobPath)}/output/</code></p>
        <div class="card-actions">${actions.join('')}</div>
      </div>
    </article>`;
  }).join('');
}

function processedGroups() {
  const items = (app.data?.items || []).filter((item) => ['processed', 'adopted'].includes(item.status));
  const groups = new Map();
  for (const item of items) {
    const key = item.original.sha256;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  }
  return [...groups.values()];
}

function currentVersion(item, step) {
  const explicit = step === 'fidelity' ? item.fidelityVersion : item.enhancedVersion;
  if (!explicit) return null;
  return (item.versions || []).find((version) => version.versionId === explicit) || null;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

// Maps a pointer position to a 0-100 value using the visible frame rect, so the
// divider, clip boundary and handle all share one normalized coordinate.
function splitPercent(clientX, left, width) {
  if (!width) return 0;
  return clamp(((clientX - left) / width) * 100, 0, 100);
}

function fitRatio(size, boxWidth, boxHeight) {
  if (!size || !size[0] || !size[1] || !boxWidth || !boxHeight) return 0;
  return Math.min(boxWidth / size[0], boxHeight / size[1]);
}

// A migration-only draft has no new images to enable. It belongs in the
// collapsed history group instead of the active review list.
function isHistoryDraft(draft) {
  return (draft.addedCount || 0) === 0 && (draft.baselineCount || 0) > 0;
}

function draftBuckets(drafts) {
  const active = [];
  const history = [];
  for (const draft of drafts || []) {
    if (isHistoryDraft(draft)) history.push(draft);
    else active.push(draft);
  }
  return { active, history };
}

// Content signature distinguishes real draft changes from unrelated polling.
function draftContentSignature(draft) {
  if (!draft) return '';
  const items = (draft.items || []).map((entry) => `${entry.itemId}:${entry.sceneId}`).join(',');
  return [
    draft.draftId,
    draft.status,
    draft.sceneCount || 0,
    draft.baselineCount || 0,
    draft.addedCount || 0,
    draft.previewUrl || '',
    items,
  ].join('|');
}

function draftSelection(draft) {
  // Drop selections for items that left the draft.
  if (!app.draftSelected[draft.draftId]) app.draftSelected[draft.draftId] = new Set();
  const selected = app.draftSelected[draft.draftId];
  const valid = new Set((draft.items || []).map((entry) => entry.itemId));
  for (const itemId of [...selected]) {
    if (!valid.has(itemId)) selected.delete(itemId);
  }
  return selected;
}

function versionSignature(item) {
  if (!item) return '';
  return [
    item.id,
    item.fidelityVersion || '',
    item.enhancedVersion || '',
    item.adoptedVersion || '',
    (item.versions || []).length,
  ].join('|');
}

function timelineHtml(item) {
  const versions = item.versions || [];
  if (!versions.length) return '';
  return `<details class="timeline" data-key="timeline-${item.id}">
    <summary>版本链 · ${versions.length} 步</summary>
    <ol>${versions.map((version) => `<li><a href="${esc(versionUrl(version))}" target="_blank" rel="noopener">${esc(version.step)}</a> · ${esc(version.processor)} · ${esc(version.size[0])} × ${esc(version.size[1])} · ${esc(version.sha256.slice(0, 12))}…</li>`).join('')}</ol>
  </details>`;
}

function viewerState() {
  if (!app.view) {
    app.view = {
      itemId: app.processedId, mode: 'side', single: 'fidelity',
      scale: null, panX: 0, panY: 0, fitScale: 0, maxPanX: 0, maxPanY: 0,
    };
  }
  if (app.view.itemId !== app.processedId) {
    app.view = {
      ...app.view, itemId: app.processedId, scale: null, panX: 0, panY: 0,
      fitScale: 0, maxPanX: 0, maxPanY: 0,
    };
  }
  return app.view;
}

function viewerMetaHtml(item) {
  return [
    tag(STATUS_LABELS[item.status] || item.status, item.status === 'failed' ? 'warn' : 'ok'),
    tag(`${item.original.size[0]} × ${item.original.size[1]}`),
    tag(item.original.format || '?'),
    item.adoptedVersion ? tag(`已采用 ${item.adoptedVersion}`, 'ok') : tag('未采用'),
  ].join('');
}

function viewerHeadHtml(item) {
  return `<div class="viewer-head">
    <div class="viewer-title"><h2 data-viewer-title title="${esc(item.filename)}">${esc(item.filename)}</h2><span class="id">${esc(item.id)}</span></div>
    <div class="card-meta" data-viewer-meta>${viewerMetaHtml(item)}</div>
  </div>`;
}

function adoptButtonHtml(item, version, kind) {
  const label = kind === 'fidelity' ? '保真版' : '增强版';
  if (!version) {
    return `<button type="button" data-action="adopt" data-kind="${kind}" data-version="" data-id="${esc(item.id)}" disabled>无${label}</button>`;
  }
  const adopted = item.adoptedVersion === version.versionId;
  return `<button type="button" class="${adopted ? '' : 'primary'}" data-action="adopt" data-kind="${kind}" data-version="${esc(version.versionId)}" data-id="${esc(item.id)}" aria-pressed="${adopted}" ${adopted ? 'disabled' : ''}>${adopted ? `已采用${label}` : `采用${label}`}</button>`;
}

function viewerToolbarHtml(item, fidelity, enhanced) {
  const view = viewerState();
  const originalSrc = item.originalUrl || `/media/${item.original.path}`;
  return `<div class="viewer-toolbar" role="toolbar" aria-label="图片查看工具">
    <div class="seg" role="group" aria-label="查看模式">
      <button type="button" data-action="view-mode" data-mode="side" aria-pressed="${view.mode === 'side'}">并排</button>
      <button type="button" data-action="view-mode" data-mode="slider" aria-pressed="${view.mode === 'slider'}">滑动</button>
      <button type="button" data-action="view-mode" data-mode="single" aria-pressed="${view.mode === 'single'}">单图</button>
    </div>
    <div class="seg" data-single-picker role="group" aria-label="单图版本" ${view.mode === 'single' ? '' : 'hidden'}>
      <button type="button" data-action="single-version" data-version-kind="original" aria-pressed="${(view.single || 'fidelity') === 'original'}">原图</button>
      <button type="button" data-action="single-version" data-version-kind="fidelity" aria-pressed="${(view.single || 'fidelity') === 'fidelity'}">保真</button>
      <button type="button" data-action="single-version" data-version-kind="enhanced" aria-pressed="${(view.single || 'fidelity') === 'enhanced'}">增强</button>
    </div>
    <div class="zoom-tools" role="group" aria-label="缩放">
      <button type="button" data-action="zoom" data-zoom-action="out" aria-label="缩小">−</button>
      <output data-zoom-label aria-live="polite">适合</output>
      <button type="button" data-action="zoom" data-zoom-action="in" aria-label="放大">+</button>
      <button type="button" data-action="zoom" data-zoom-action="fit">适合窗口</button>
      <button type="button" data-action="zoom" data-zoom-action="actual">100%</button>
    </div>
    <div class="viewer-actions">
      ${adoptButtonHtml(item, fidelity, 'fidelity')}
      ${adoptButtonHtml(item, enhanced, 'enhanced')}
      <a class="tag" href="${esc(originalSrc)}" target="_blank" rel="noopener">原图 ↗</a>
    </div>
  </div>`;
}

function paneHtml(kind, label, src, version) {
  const versionId = version ? version.versionId : '缺失';
  return `<figure class="pane" data-pane="${kind}">
    <figcaption class="pane-label">${esc(label)} · <span data-version-label="${kind}">${esc(versionId)}</span></figcaption>
    <div class="pane-viewport" data-viewport><div class="image-wrap" data-image-wrap="${kind}"><img src="${esc(src)}" alt="${esc(label)}"></div></div>
  </figure>`;
}

function viewerStageHtml(item, fidelity, enhanced) {
  const view = viewerState();
  const fidSrc = fidelity ? versionUrl(fidelity) : PLACEHOLDER_IMAGE;
  const enhSrc = enhanced ? versionUrl(enhanced) : PLACEHOLDER_IMAGE;
  const originalSrc = item.originalUrl || `/media/${item.original.path}`;
  const single = view.single || 'fidelity';
  const singleSrc = single === 'original' ? originalSrc : single === 'enhanced' ? enhSrc : fidSrc;
  const split = Math.round(app.slider[item.id] ?? 50);
  return `<div class="viewer-stage" data-view-stage>
    <div class="view-pane side-pane" data-view-pane="side" ${view.mode === 'side' ? '' : 'hidden'}>
      ${paneHtml('fidelity', '原作保真版', fidSrc, fidelity)}
      ${paneHtml('enhanced', '网站增强版', enhSrc, enhanced)}
    </div>
    <div class="view-pane slider-pane" data-view-pane="slider" ${view.mode === 'slider' ? '' : 'hidden'}>
      <div class="slider-legend"><span>原作保真版</span><span>网站增强版</span></div>
      <div class="slider-frame" data-slider-frame data-slider-box="${esc(item.id)}">
        <div class="slider-base"><img class="slider-image" data-slider-image="fidelity" src="${esc(fidSrc)}" alt="原作保真版"></div>
        <div class="slider-overlay" data-slider-clip><img class="slider-image" data-slider-image="enhanced" src="${esc(enhSrc)}" alt="网站增强版"></div>
        <div class="slider-handle" data-slider-handle role="slider" tabindex="0" aria-label="拖动分割线对比保真版和增强版" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${split}" aria-valuetext="分割位置 ${split}%">
          <span class="slider-knob" aria-hidden="true"></span>
        </div>
        <span class="slider-caption" data-slider-caption-left>原作保真版</span>
        <span class="slider-caption" data-slider-caption-right>网站增强版</span>
      </div>
    </div>
    <div class="view-pane single-pane" data-view-pane="single" ${view.mode === 'single' ? '' : 'hidden'}>
      <div class="pane-viewport" data-viewport><div class="image-wrap" data-image-wrap="single"><img data-single-image src="${esc(singleSrc)}" alt="单图查看"></div></div>
    </div>
  </div>`;
}

function viewerDetailsHtml(item) {
  const versions = item.versions || [];
  return `<dl class="meta-grid">
    <div><dt>文件</dt><dd>${esc(item.filename)}</dd></div>
    <div><dt>ID</dt><dd>${esc(item.id)}</dd></div>
    <div><dt>原图 SHA-256</dt><dd><code>${esc(item.original.sha256)}</code></dd></div>
    <div><dt>接收时间</dt><dd>${esc(item.receivedAt || '—')}</dd></div>
    <div><dt>当前保真</dt><dd>${esc(item.fidelityVersion || '—')}</dd></div>
    <div><dt>当前增强</dt><dd>${esc(item.enhancedVersion || '—')}</dd></div>
    <div><dt>已采用</dt><dd>${esc(item.adoptedVersion || '—')}</dd></div>
    <div><dt>版本数</dt><dd>${versions.length}</dd></div>
  </dl>${timelineHtml(item)}`;
}

function viewerFootHtml(item) {
  const originalSrc = item.originalUrl || `/media/${item.original.path}`;
  const adopted = item.adoptedVersion ? tag(`已采用 ${item.adoptedVersion}`, 'ok') : '';
  return `<div class="viewer-foot">
    <div class="viewer-foot-row">
      <span class="viewer-foot-name" title="${esc(item.filename)}">${esc(item.filename)}</span>
      <span class="id">${esc(item.id)}</span>
      ${tag(`${item.original.size[0]} × ${item.original.size[1]}`)}
      <span data-viewer-adopted>${adopted}</span>
      <a class="link" href="${esc(originalSrc)}" target="_blank" rel="noopener">打开原图 ↗</a>
    </div>
    <details class="viewer-details" data-key="viewer-details">
      <summary>文件与版本详情</summary>
      <div data-viewer-details-body>${viewerDetailsHtml(item)}</div>
    </details>
  </div>`;
}

function viewerHtml(item) {
  const fidelity = currentVersion(item, 'fidelity');
  const enhanced = currentVersion(item, 'enhanced');
  return `${viewerHeadHtml(item)}${viewerToolbarHtml(item, fidelity, enhanced)}${viewerStageHtml(item, fidelity, enhanced)}${viewerFootHtml(item)}`;
}

function buildProcessedViewer(item) {
  const viewer = document.getElementById('processed-viewer');
  viewer.innerHTML = viewerHtml(item);
  app.viewerItemId = item.id;
  app.viewerVersionSig = versionSignature(item);
  restoreDetails();
  applyViewMode();
  requestAnimationFrame(layoutViewer);
}

function updateAdoptButton(button, item, kind) {
  const version = kind === 'fidelity' ? currentVersion(item, 'fidelity') : currentVersion(item, 'enhanced');
  const label = kind === 'fidelity' ? '保真版' : '增强版';
  if (!version) {
    button.hidden = true;
    button.disabled = true;
    button.dataset.version = '';
    button.textContent = `无${label}`;
    return;
  }
  button.hidden = false;
  button.dataset.version = version.versionId;
  const adopted = item.adoptedVersion === version.versionId;
  button.disabled = adopted;
  button.classList.toggle('primary', !adopted);
  button.setAttribute('aria-pressed', String(adopted));
  button.textContent = adopted ? `已采用${label}` : `采用${label}`;
}

function syncSingleImage(item) {
  const viewer = document.getElementById('processed-viewer');
  if (!viewer) return;
  const view = viewerState();
  const fidelity = currentVersion(item, 'fidelity');
  const enhanced = currentVersion(item, 'enhanced');
  const single = view.single || 'fidelity';
  const src = single === 'original'
    ? (item.originalUrl || `/media/${item.original.path}`)
    : single === 'enhanced'
      ? (enhanced ? versionUrl(enhanced) : PLACEHOLDER_IMAGE)
      : (fidelity ? versionUrl(fidelity) : PLACEHOLDER_IMAGE);
  const image = viewer.querySelector('[data-single-image]');
  if (image && image.getAttribute('src') !== src) image.src = src;
}

function syncProcessedViewer(item) {
  const viewer = document.getElementById('processed-viewer');
  if (!viewer || app.viewerItemId !== item.id) return;
  const fidelity = currentVersion(item, 'fidelity');
  const enhanced = currentVersion(item, 'enhanced');
  const fidSrc = fidelity ? versionUrl(fidelity) : PLACEHOLDER_IMAGE;
  const enhSrc = enhanced ? versionUrl(enhanced) : PLACEHOLDER_IMAGE;
  const setImage = (selector, src) => {
    const image = viewer.querySelector(selector);
    if (image && image.getAttribute('src') !== src) image.src = src;
  };
  setImage('[data-image-wrap="fidelity"] img', fidSrc);
  setImage('[data-image-wrap="enhanced"] img', enhSrc);
  setImage('[data-slider-image="fidelity"]', fidSrc);
  setImage('[data-slider-image="enhanced"]', enhSrc);
  const labels = { fidelity: fidelity ? fidelity.versionId : '缺失', enhanced: enhanced ? enhanced.versionId : '缺失' };
  viewer.querySelectorAll('[data-version-label]').forEach((element) => {
    element.textContent = labels[element.dataset.versionLabel] || '缺失';
  });
  const title = viewer.querySelector('[data-viewer-title]');
  if (title) { title.textContent = item.filename; title.title = item.filename; }
  const meta = viewer.querySelector('[data-viewer-meta]');
  if (meta) meta.innerHTML = viewerMetaHtml(item);
  const adopted = viewer.querySelector('[data-viewer-adopted]');
  if (adopted) adopted.innerHTML = item.adoptedVersion ? tag(`已采用 ${item.adoptedVersion}`, 'ok') : '';
  const originalSrc = item.originalUrl || `/media/${item.original.path}`;
  const footLink = viewer.querySelector('.viewer-foot a.link');
  if (footLink) footLink.href = originalSrc;
  const details = viewer.querySelector('[data-viewer-details-body]');
  if (details) details.innerHTML = viewerDetailsHtml(item);
  restoreDetails();
  viewer.querySelectorAll('[data-action="adopt"]').forEach((button) => updateAdoptButton(button, item, button.dataset.kind));
  syncSingleImage(item);
  applyViewMode();
  layoutViewer();
}

function renderProcessed() {
  const groups = processedGroups();
  const filtered = groups.filter((group) => !(app.onlyUnadopted && group.some((entry) => entry.adoptedVersion)));
  const list = document.getElementById('processed-list');
  const viewer = document.getElementById('processed-viewer');
  const count = document.getElementById('processed-count');
  const signature = filtered.map((group) => {
    const item = group[0];
    return [item.id, item.filename, item.status, item.adoptedVersion || '',
      item.fidelityVersion || '', item.enhancedVersion || '', group.length].join(':');
  }).join('|');
  if (!filtered.length) {
    app.processedId = null;
    app.viewerItemId = null;
    app.viewerVersionSig = '';
    if (app.processedListSig !== signature) {
      app.processedListSig = signature;
      list.innerHTML = empty('没有可审核的已处理图片。');
    }
    if (count) count.textContent = '0 张';
    viewer.innerHTML = '<div class="viewer-empty">还没有处理完成的图片。去“待处理”开始一张。</div>';
    return;
  }
  if (!filtered.some((group) => group[0].id === app.processedId)) app.processedId = filtered[0][0].id;
  if (signature !== app.processedListSig) {
    app.processedListSig = signature;
    list.innerHTML = filtered.map((group) => processedListItem(group[0], group)).join('');
  } else {
    list.querySelectorAll('[data-action="select-processed"]').forEach((button) => {
      button.setAttribute('aria-current', String(button.dataset.id === app.processedId));
    });
  }
  if (count) count.textContent = `${filtered.length} 张`;
  const group = filtered.find((entry) => entry[0].id === app.processedId);
  const item = group[0];
  if (app.viewerItemId !== item.id) buildProcessedViewer(item);
  else syncProcessedViewer(item);
  app.viewerVersionSig = versionSignature(item);
}

function processedListItem(item, group) {
  const adopted = group.some((entry) => entry.adoptedVersion);
  return `<button type="button" class="review-item" data-action="select-processed" data-id="${esc(item.id)}" aria-current="${item.id === app.processedId}">
    <img src="${esc(item.thumbUrl)}" alt="" loading="lazy">
    <span class="review-item-body">
      <span class="review-item-name" title="${esc(item.filename)}">${esc(item.filename)}</span>
      <span class="review-item-sub">${esc(item.original.size[0])} × ${esc(item.original.size[1])}</span>
      <span class="review-item-meta">${tag(STATUS_LABELS[item.status] || item.status, item.status === 'failed' ? 'warn' : 'ok')}${adopted ? tag('已采用', 'ok') : ''}</span>
    </span>
  </button>`;
}

function draftMetaHtml(draft) {
  return [
    tag(`${draft.sceneCount} 张场景`),
    tag(`基线 ${draft.baselineCount}`),
    tag(`新增 ${draft.addedCount}`, draft.addedCount ? 'blue' : ''),
    tag(draft.status, draft.status === 'enabled' ? 'ok' : 'blue'),
  ].join('');
}

function draftOptionsHtml() {
  const drafts = app.data?.drafts || [];
  // Without an active draft, do not let the browser visually preselect the first option.
  const placeholder = app.activeDraftId ? '' : '<option value="" selected disabled>请选择草稿…</option>';
  return placeholder + drafts.map((draft) => `<option value="${esc(draft.draftId)}" ${draft.draftId === app.activeDraftId ? 'selected' : ''}>${esc(draft.name)}${isHistoryDraft(draft) ? '（历史）' : ''}</option>`).join('');
}

function draftHint(draft) {
  const selected = draftSelection(draft);
  const added = draft.items || [];
  if (draft.status === 'enabled') return '已启用，正式主页已包含这份草稿的场景。';
  if (!added.length) return '历史迁移核对没有新增图片，不产生启用操作；展开左侧历史分组可查看 54 张基线预览。';
  if (!selected.size) return '勾选至少一张新增图片后才能启用；启用前会再次确认。';
  return `已选 ${selected.size} 张；启用会切换正式主页，失败会自动恢复旧站点。`;
}

function draftEmptyHtml() {
  const hasDrafts = (app.data?.drafts || []).length > 0;
  return `<div class="draft-empty">
    <p class="drop-title">暂无待审核草稿</p>
    <p class="card-note">在“已处理”里采用图片后，点“加入草稿”建立新的审核草稿。历史迁移核对收在左侧折叠分组里，展开后可查看 54 张基线预览。</p>
    ${hasDrafts ? `<select class="draft-select" data-draft-select aria-label="选择草稿">${draftOptionsHtml()}</select>` : ''}
  </div>`;
}

function draftListItem(draft) {
  const history = isHistoryDraft(draft);
  return `<button type="button" class="draft-item" data-action="select-draft" data-id="${esc(draft.draftId)}" aria-current="${draft.draftId === app.activeDraftId}">
    <span class="draft-item-name" title="${esc(draft.name)}">${esc(draft.name)}</span>
    <span class="draft-item-meta">${history ? '历史基线 · ' : ''}场景 ${draft.sceneCount} · 新增 ${draft.addedCount}${draft.status === 'enabled' ? ' · 已启用' : ''}</span>
  </button>`;
}

function draftPreviewHtml(draft) {
  const selected = draftSelection(draft);
  const added = draft.items || [];
  const enabled = draft.status === 'enabled';
  const rows = added.map((entry) => {
    const item = itemById(entry.itemId);
    return `<label class="draft-check"><input type="checkbox" data-draft-item="${esc(draft.draftId)}" data-item="${esc(entry.itemId)}" ${selected.has(entry.itemId) ? 'checked' : ''} ${enabled ? 'disabled' : ''}> <span class="draft-check-name">${esc(item?.filename || entry.itemId)}</span><span class="id">${esc(entry.sceneId)}</span></label>`;
  }).join('');
  const canEnable = !enabled && added.length > 0 && selected.size > 0;
  return `<div class="draft-preview-head">
    <div class="draft-preview-title"><h2 data-draft-title title="${esc(draft.name)}">${esc(draft.name)}</h2><span class="id" data-draft-id>${esc(draft.draftId)}</span></div>
    <div class="draft-preview-tools">
      <select class="draft-select" data-draft-select aria-label="活动草稿">${draftOptionsHtml()}</select>
      <div class="card-meta" data-draft-meta>${draftMetaHtml(draft)}</div>
      <div class="card-actions">
        <a class="tag" href="${esc(draft.previewUrl)}" target="_blank" rel="noopener">工具内预览 ↗</a>
        <a class="tag" href="http://127.0.0.1:8766${esc(draft.previewUrl)}" target="_blank" rel="noopener">8766 全屏 ↗</a>
        <button type="button" data-action="toggle-draft-expand" aria-expanded="${app.draftExpanded}">${app.draftExpanded ? '收起侧栏' : '展开大预览'}</button>
      </div>
    </div>
  </div>
  <div class="draft-frame-wrap"><iframe data-draft-frame src="${esc(draft.previewUrl)}" title="${esc(draft.name)} 的内嵌预览"></iframe></div>
  <div class="draft-preview-foot">
    <div class="draft-selection-head"><span>新增图片</span><span class="id" data-draft-selection-head>${added.length ? `${selected.size}/${added.length} 已选` : '无新增图片'}</span></div>
    ${added.length ? `<div class="draft-selection" data-draft-selection>${rows}</div>` : '<p class="card-note">这份草稿只包含已启用的 54 张基线，没有新增图片；历史核对不产生启用操作。</p>'}
    <div class="draft-actions">
      <button type="button" class="primary" data-action="enable-draft" data-id="${esc(draft.draftId)}" ${canEnable ? '' : 'disabled'}>启用选中图片</button>
      <button type="button" data-action="cancel-draft-items" data-id="${esc(draft.draftId)}" ${enabled || !selected.size ? 'disabled' : ''}>取消选中图片</button>
      ${enabled ? `<span class="card-note">${tag('已启用', 'ok')} ${esc(draft.enabledAt || '')}</span>` : ''}
    </div>
    <p class="draft-hint" data-draft-hint>${esc(draftHint(draft))}</p>
  </div>`;
}

function buildDraftPreview(draft) {
  const preview = document.getElementById('draft-preview');
  preview.innerHTML = draftPreviewHtml(draft);
  app.draftPreviewId = draft.draftId;
  app.draftPreviewStatus = draft.status;
  app.draftPreviewSig = draftContentSignature(draft);
  restoreDetails();
}

function syncDraftPreview(draft) {
  const preview = document.getElementById('draft-preview');
  if (!preview || app.draftPreviewId !== draft.draftId) return;
  const title = preview.querySelector('[data-draft-title]');
  if (title) { title.textContent = draft.name; title.title = draft.name; }
  const id = preview.querySelector('[data-draft-id]');
  if (id) id.textContent = draft.draftId;
  const meta = preview.querySelector('[data-draft-meta]');
  if (meta) meta.innerHTML = draftMetaHtml(draft);
  const select = preview.querySelector('[data-draft-select]');
  if (select) select.innerHTML = draftOptionsHtml();
  const toggle = preview.querySelector('[data-action="toggle-draft-expand"]');
  if (toggle) {
    toggle.textContent = app.draftExpanded ? '收起侧栏' : '展开大预览';
    toggle.setAttribute('aria-expanded', String(app.draftExpanded));
  }
  const selected = draftSelection(draft);
  const added = draft.items || [];
  const enabled = draft.status === 'enabled';
  preview.querySelectorAll('[data-draft-item]').forEach((input) => {
    input.checked = selected.has(input.dataset.item);
    input.disabled = enabled;
  });
  const head = preview.querySelector('[data-draft-selection-head]');
  if (head) head.textContent = added.length ? `${selected.size}/${added.length} 已选` : '无新增图片';
  const enable = preview.querySelector('[data-action="enable-draft"]');
  if (enable) enable.disabled = enabled || !added.length || !selected.size;
  const cancel = preview.querySelector('[data-action="cancel-draft-items"]');
  if (cancel) cancel.disabled = enabled || !selected.size;
  const hint = preview.querySelector('[data-draft-hint]');
  if (hint) hint.textContent = draftHint(draft);
}

function renderDrafts() {
  const drafts = app.data?.drafts || [];
  const { active, history } = draftBuckets(drafts);
  const list = document.getElementById('drafts-list');
  const historyList = document.getElementById('drafts-history-list');
  const historyBox = document.getElementById('draft-history');
  const count = document.getElementById('drafts-count');
  const historyCount = document.getElementById('draft-history-count');
  const preview = document.getElementById('draft-preview');
  const layout = document.getElementById('drafts-layout');
  if (layout) layout.classList.toggle('expanded', app.draftExpanded);
  if (!drafts.length) {
    app.activeDraftId = null;
    app.draftPreviewId = null;
    app.draftPreviewStatus = '';
    app.draftPreviewSig = '';
    app.draftListSig = '';
    list.innerHTML = empty('还没有草稿。在“已处理”里采用图片后，可以加入草稿。');
    historyList.innerHTML = '';
    historyBox.hidden = true;
    if (count) count.textContent = '0 份';
    preview.innerHTML = draftEmptyHtml();
    return;
  }
  if (!drafts.some((draft) => draft.draftId === app.activeDraftId)) {
    app.activeDraftId = active[0]?.draftId || null;
  }
  const signature = drafts.map((draft) => [draft.draftId, draft.name, draft.sceneCount,
    draft.addedCount, draft.baselineCount, draft.status].join(':')).join('|')
    + `|active:${app.activeDraftId}`;
  if (signature !== app.draftListSig) {
    app.draftListSig = signature;
    list.innerHTML = active.length ? active.map(draftListItem).join('') : empty('没有待审核的新增图片草稿。');
    historyList.innerHTML = history.map(draftListItem).join('');
    historyBox.hidden = !history.length;
    if (count) count.textContent = `${active.length} 份`;
    if (historyCount) historyCount.textContent = history.length ? `${history.length} 份` : '';
  } else {
    document.querySelectorAll('[data-action="select-draft"]').forEach((button) => {
      button.setAttribute('aria-current', String(button.dataset.id === app.activeDraftId));
    });
  }
  const draft = draftById(app.activeDraftId);
  if (!draft) {
    app.draftPreviewId = null;
    app.draftPreviewStatus = '';
    app.draftPreviewSig = '';
    preview.innerHTML = draftEmptyHtml();
    return;
  }
  const previewSig = draftContentSignature(draft);
  if (app.draftPreviewId !== draft.draftId || app.draftPreviewStatus !== draft.status
      || app.draftPreviewSig !== previewSig) {
    buildDraftPreview(draft);
  } else {
    syncDraftPreview(draft);
  }
}

function restoreDetails() {
  document.querySelectorAll('details[data-key]').forEach((details) => {
    details.open = app.openDetails.has(details.dataset.key);
  });
}

function clampPan(view) {
  view.panX = clamp(view.panX, -view.maxPanX, view.maxPanX);
  view.panY = clamp(view.panY, -view.maxPanY, view.maxPanY);
}

function applyViewTransform() {
  const viewer = document.getElementById('processed-viewer');
  if (!viewer) return;
  const view = viewerState();
  const fit = view.fitScale || 1;
  const relative = fit ? (view.scale ?? fit) / fit : 1;
  viewer.querySelectorAll('[data-image-wrap]').forEach((wrap) => {
    wrap.style.transform = `translate(-50%, -50%) translate(${view.panX}px, ${view.panY}px) scale(${relative})`;
  });
  viewer.querySelectorAll('[data-slider-image]').forEach((image) => {
    image.style.transform = `translate(${view.panX}px, ${view.panY}px) scale(${relative})`;
  });
  const label = viewer.querySelector('[data-zoom-label]');
  if (label) label.textContent = view.scale == null ? '适合' : `${Math.round((view.scale) * 100)}%`;
}

function placeImage(wrap, size, fit, view) {
  if (!wrap || !fit) return;
  const actual = view.scale ?? fit;
  const relative = fit ? actual / fit : 1;
  wrap.style.width = `${size[0] * fit}px`;
  wrap.style.height = `${size[1] * fit}px`;
  wrap.style.transform = `translate(-50%, -50%) translate(${view.panX}px, ${view.panY}px) scale(${relative})`;
}

function layoutViewer() {
  const panel = document.getElementById('panel-processed');
  const viewer = document.getElementById('processed-viewer');
  if (!panel || panel.hidden || !viewer) return;
  const item = itemById(app.processedId);
  if (!item) return;
  const stage = viewer.querySelector('[data-view-stage]');
  if (!stage) return;
  const rect = stage.getBoundingClientRect();
  if (rect.width < 40 || rect.height < 40) return;
  const view = viewerState();
  const fidelity = currentVersion(item, 'fidelity');
  const enhanced = currentVersion(item, 'enhanced');
  const fidSize = fidelity ? fidelity.size : item.original.size;
  const enhSize = enhanced ? enhanced.size : item.original.size;
  if (view.mode === 'side') {
    const fidViewport = viewer.querySelector('[data-pane="fidelity"] .pane-viewport');
    const enhViewport = viewer.querySelector('[data-pane="enhanced"] .pane-viewport');
    const fidRect = fidViewport ? fidViewport.getBoundingClientRect() : { width: 40, height: 40 };
    const enhRect = enhViewport ? enhViewport.getBoundingClientRect() : { width: 40, height: 40 };
    const paneWidth = Math.max(40, Math.min(fidRect.width, enhRect.width));
    const paneHeight = Math.max(40, Math.min(fidRect.height, enhRect.height));
    const fit = Math.min(fitRatio(fidSize, paneWidth, paneHeight), fitRatio(enhSize, paneWidth, paneHeight));
    view.fitScale = fit;
    const scale = view.scale ?? fit;
    view.maxPanX = Math.max(0, (Math.min(fidSize[0], enhSize[0]) * scale - paneWidth) / 2);
    view.maxPanY = Math.max(0, (Math.min(fidSize[1], enhSize[1]) * scale - paneHeight) / 2);
    clampPan(view);
    placeImage(viewer.querySelector('[data-image-wrap="fidelity"]'), fidSize, fit, view);
    placeImage(viewer.querySelector('[data-image-wrap="enhanced"]'), enhSize, fit, view);
  } else if (view.mode === 'single') {
    const single = view.single || 'fidelity';
    const size = single === 'original' ? item.original.size : single === 'enhanced' ? enhSize : fidSize;
    const singleViewport = viewer.querySelector('[data-view-pane="single"] .pane-viewport');
    const singleRect = singleViewport ? singleViewport.getBoundingClientRect() : { width: 40, height: 40 };
    const boxWidth = Math.max(40, singleRect.width);
    const boxHeight = Math.max(40, singleRect.height);
    const fit = fitRatio(size, boxWidth, boxHeight);
    view.fitScale = fit;
    const scale = view.scale ?? fit;
    view.maxPanX = Math.max(0, (size[0] * scale - boxWidth) / 2);
    view.maxPanY = Math.max(0, (size[1] * scale - boxHeight) / 2);
    clampPan(view);
    placeImage(viewer.querySelector('[data-image-wrap="single"]'), size, fit, view);
  } else {
    const sliderPane = viewer.querySelector('[data-view-pane="slider"]');
    const paneRect = sliderPane ? sliderPane.getBoundingClientRect() : { width: 40, height: 40 };
    const boxWidth = Math.max(40, paneRect.width - 36);
    const boxHeight = Math.max(40, paneRect.height - 28);
    const fit = Math.min(fitRatio(fidSize, boxWidth, boxHeight), fitRatio(enhSize, boxWidth, boxHeight));
    const frame = viewer.querySelector('[data-slider-frame]');
    if (frame) {
      frame.style.width = `${fidSize[0] * fit}px`;
      frame.style.height = `${fidSize[1] * fit}px`;
    }
    view.fitScale = fit;
    const scale = view.scale ?? fit;
    view.maxPanX = Math.max(0, (fidSize[0] * scale - fidSize[0] * fit) / 2);
    view.maxPanY = Math.max(0, (fidSize[1] * scale - fidSize[1] * fit) / 2);
    clampPan(view);
    applyViewTransform();
  }
  const zoomLabel = viewer.querySelector('[data-zoom-label]');
  if (zoomLabel) zoomLabel.textContent = view.scale == null ? '适合' : `${Math.round((view.scale) * 100)}%`;
  setSplit(app.slider[item.id] ?? 50);
}

function applyViewMode() {
  const panel = document.getElementById('panel-processed');
  const viewer = document.getElementById('processed-viewer');
  if (!panel || !viewer || panel.hidden) return;
  const item = itemById(app.processedId);
  if (!item) return;
  const view = viewerState();
  viewer.querySelectorAll('[data-action="view-mode"]').forEach((button) => {
    button.setAttribute('aria-pressed', String(button.dataset.mode === view.mode));
  });
  viewer.querySelectorAll('[data-view-pane]').forEach((pane) => {
    pane.hidden = pane.dataset.viewPane !== view.mode;
  });
  const picker = viewer.querySelector('[data-single-picker]');
  if (picker) picker.hidden = view.mode !== 'single';
  viewer.querySelectorAll('[data-action="single-version"]').forEach((button) => {
    button.setAttribute('aria-pressed', String(button.dataset.versionKind === (view.single || 'fidelity')));
  });
  syncSingleImage(item);
}

function setSplit(value) {
  const viewer = document.getElementById('processed-viewer');
  const itemId = app.processedId;
  if (!viewer || !itemId) return;
  const box = viewer.querySelector(`[data-slider-box="${itemId}"]`);
  if (!box) return;
  const split = clamp(Number(value) || 0, 0, 100);
  app.slider[itemId] = split;
  const overlay = box.querySelector('[data-slider-clip]');
  if (overlay) overlay.style.clipPath = `inset(0 0 0 ${split}%)`;
  const handle = box.querySelector('[data-slider-handle]');
  if (handle) {
    handle.style.left = `${split}%`;
    handle.setAttribute('aria-valuenow', String(Math.round(split)));
    handle.setAttribute('aria-valuetext', `分割位置 ${Math.round(split)}%`);
  }
  const left = box.querySelector('[data-slider-caption-left]');
  const right = box.querySelector('[data-slider-caption-right]');
  if (left) left.style.opacity = split > 1 ? '1' : '0';
  if (right) right.style.opacity = split < 99 ? '1' : '0';
}

function isZoomed() {
  const view = viewerState();
  if (!view.fitScale) return false;
  return (view.scale ?? view.fitScale) > view.fitScale * 1.001;
}

function zoomView(action) {
  const view = viewerState();
  const fit = view.fitScale || 1;
  if (action === 'fit') {
    view.scale = null;
    view.panX = 0;
    view.panY = 0;
  } else if (action === 'actual') {
    view.scale = 1;
    view.panX = 0;
    view.panY = 0;
  } else {
    const base = view.scale ?? fit;
    const next = action === 'in' ? base * 1.25 : base / 1.25;
    view.scale = clamp(next, Math.min(fit, 1), 8);
  }
  layoutViewer();
}

function beginSplitDrag(event, frame) {
  event.preventDefault();
  event.stopPropagation();
  const handle = frame.querySelector('[data-slider-handle]');
  if (handle) handle.focus({ preventScroll: true });
  const rect = frame.getBoundingClientRect();
  setSplit(splitPercent(event.clientX, rect.left, rect.width));
  app.interacting = true;
  document.body.classList.add('is-dragging-split');
  const move = (moveEvent) => {
    const box = frame.getBoundingClientRect();
    setSplit(splitPercent(moveEvent.clientX, box.left, box.width));
  };
  const finish = () => {
    window.removeEventListener('pointermove', move);
    window.removeEventListener('pointerup', finish);
    window.removeEventListener('pointercancel', finish);
    window.removeEventListener('blur', finish);
    app.interacting = false;
    document.body.classList.remove('is-dragging-split');
    flushPendingState();
  };
  window.addEventListener('pointermove', move);
  window.addEventListener('pointerup', finish);
  window.addEventListener('pointercancel', finish);
  window.addEventListener('blur', finish);
}

function beginPan(event, viewport) {
  event.preventDefault();
  event.stopPropagation();
  app.interacting = true;
  document.body.classList.add('is-panning');
  const view = viewerState();
  const startX = event.clientX;
  const startY = event.clientY;
  const startPanX = view.panX;
  const startPanY = view.panY;
  const move = (moveEvent) => {
    view.panX = startPanX + moveEvent.clientX - startX;
    view.panY = startPanY + moveEvent.clientY - startY;
    clampPan(view);
    applyViewTransform();
  };
  const finish = () => {
    window.removeEventListener('pointermove', move);
    window.removeEventListener('pointerup', finish);
    window.removeEventListener('pointercancel', finish);
    window.removeEventListener('blur', finish);
    app.interacting = false;
    document.body.classList.remove('is-panning');
    flushPendingState();
  };
  window.addEventListener('pointermove', move);
  window.addEventListener('pointerup', finish);
  window.addEventListener('pointercancel', finish);
  window.addEventListener('blur', finish);
}

function flushPendingState() {
  if (!app.pendingState) return;
  app.pendingState = null;
  render();
}

function layoutWorkbench() {
  const panel = document.getElementById(`panel-${app.tab}`);
  if (!panel || panel.hidden) return;
  const top = panel.getBoundingClientRect().top + window.scrollY;
  const height = Math.max(420, window.innerHeight - top - 6);
  panel.style.setProperty('--panel-h', `${Math.round(height)}px`);
  if (app.tab === 'processed') layoutViewer();
}

function applyState(data) {
  app.data = data;
  if (app.interacting) {
    app.pendingState = data;
    return;
  }
  render();
}

function renderEnabled() {
  const scenes = app.data?.enabled || [];
  const list = document.getElementById('enabled-list');
  if (!scenes.length) { list.innerHTML = empty('还没有已启用场景。'); return; }
  list.innerHTML = scenes.map((scene) => `<figure class="tile">
    <img src="${esc(scene.thumbUrl)}" alt="${esc(scene.title || scene.id)}" loading="lazy">
    <figcaption>${esc(scene.id)}<br>${esc(TIME_LABELS[scene.time] || '不分时段')} · ${tag('只读')}</figcaption>
  </figure>`).join('');
}

function render() {
  if (!app.data) return;
  const counts = app.data.counts || {};
  const countsFor = {
    deliver: (counts.received || 0) + (counts.previewed || 0),
    pending: (counts.received || 0) + (counts.previewed || 0) + (counts.planned || 0)
      + (counts.waiting_ai || 0) + (counts.processing_local || 0) + (counts.failed || 0) + (counts.cancelled || 0),
    ai: (app.data.tasks || []).filter((task) => task.status === 'waiting').length,
    processed: (counts.processed || 0) + (counts.adopted || 0),
    drafts: (app.data.drafts || []).filter((draft) => draft.status !== 'enabled').length,
    enabled: (app.data.enabled || []).length,
  };
  document.querySelectorAll('[data-count]').forEach((element) => {
    const value = countsFor[element.dataset.count];
    element.textContent = value ? String(value) : '';
  });
  document.querySelectorAll('[role="tab"]').forEach((button) => {
    button.setAttribute('aria-selected', String(button.dataset.tab === app.tab));
  });
  document.querySelectorAll('.panel').forEach((panel) => {
    panel.hidden = panel.id !== `panel-${app.tab}`;
  });
  const worker = document.getElementById('worker');
  worker.textContent = app.data.worker?.busy ? `处理中 · ${app.data.worker.current || ''}` : '待机';
  worker.classList.toggle('busy', Boolean(app.data.worker?.busy));
  renderDeliver();
  renderPending();
  renderAI();
  renderProcessed();
  renderDrafts();
  renderEnabled();
  restoreDetails();
  layoutWorkbench();
}

async function loadState() {
  try {
    applyState(await api('/api/state'));
  } catch (error) {
    toast(error.message, true);
  }
}

function startPolling() {
  clearInterval(app.timer);
  app.timer = setInterval(async () => {
    if (app.busy) return;
    try {
      const data = await api('/api/state');
      if (!app.data || data.revision !== app.data.revision) applyState(data);
    } catch {
      // A transient poll failure is reported by the next user action.
    }
  }, 2000);
}

async function startItems(ids, confirm = false) {
  if (!ids.length) { toast('先勾选要处理的图片。', true); return; }
  app.busy = true;
  try {
    const data = await api('/api/start', {
      method: 'POST',
      body: JSON.stringify({ itemIds: ids, settings: batchSettings(), overrides: app.overrides, confirm }),
    });
    toast(`已安排 ${data.plans.length} 张图片。`);
    app.selected.clear();
    await loadState();
  } catch (error) {
    if (error.payload?.confirmationRequired && !confirm) {
      const lines = error.payload.plans.map((plan) => {
        const reasons = (plan.uncertainties || []).map((entry) => entry.reason || entry.kind);
        return `${plan.itemId} · ${reasons.length ? reasons.join('；') : `置信 ${Math.round((plan.confidence || 0) * 100)}%`}`;
      });
      if (window.confirm(`这些图片有不确定项，需要先确认：\n\n${lines.join('\n')}\n\n继续会按当前设置处理；去字会生成 AI 任务。`)) {
        app.busy = false;
        return startItems(ids, true);
      }
      toast('已停在确认前；没有生成任务。');
      return;
    }
    toast(error.message, true);
  } finally {
    app.busy = false;
  }
}

async function uploadFiles(files) {
  const images = [...files].filter((file) => file.type.startsWith('image/') || /\.(png|jpe?g|webp|bmp|tiff?|gif)$/i.test(file.name));
  if (!images.length) { toast('没有可用的图片文件。', true); return; }
  const status = document.getElementById('drop-status');
  let done = 0;
  for (const file of images) {
    status.textContent = `正在复制 ${file.name}（${done + 1}/${images.length}）…`;
    try {
      const data = await api(`/api/deliver?name=${encodeURIComponent(file.name)}`, {
        method: 'POST', body: file, headers: {},
      });
      app.selected.add(data.item.id);
      done += 1;
    } catch (error) {
      status.textContent = `${file.name}: ${error.message}`;
      status.classList.add('error');
      toast(error.message, true);
    }
  }
  status.textContent = `已接收 ${done} 张；原图只复制，不移动。`;
  status.classList.toggle('error', done !== images.length);
  await loadState();
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const area = document.createElement('textarea');
    area.value = text;
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.append(area);
    area.select();
    const ok = document.execCommand('copy');
    area.remove();
    return ok;
  }
}

document.addEventListener('click', async (event) => {
  const tab = event.target.closest('[role="tab"]');
  if (tab) {
    app.tab = tab.dataset.tab;
    render();
    return;
  }
  const button = event.target.closest('[data-action]');
  if (!button) return;
  const action = button.dataset.action;
  const id = button.dataset.id;
  try {
    if (action === 'start') {
      await startItems([id]);
    } else if (action === 'save-settings') {
      const root = document.querySelector(`[data-settings-for="${id}"]`);
      app.overrides[id] = readSettings(root);
      toast(`${id} 的单张设置已保存。`);
      render();
    } else if (action === 'clear-settings') {
      delete app.overrides[id];
      toast(`${id} 恢复批次设置。`);
      render();
    } else if (action === 'cancel') {
      const data = await api('/api/cancel', { method: 'POST', body: JSON.stringify({ itemIds: [id] }) });
      toast(`已请求取消 ${data.items.length} 张。`);
      await loadState();
    } else if (action === 'retry') {
      const data = await api('/api/retry', { method: 'POST', body: JSON.stringify({ itemIds: [id] }) });
      toast(`已重新安排 ${data.items.length} 张。`);
      await loadState();
    } else if (action === 'adopt') {
      await api('/api/adopt', { method: 'POST', body: JSON.stringify({ itemId: id, versionId: button.dataset.version }) });
      toast(`已采用 ${id}。`);
      await loadState();
    } else if (action === 'select-processed') {
      app.processedId = id;
      renderProcessed();
      requestAnimationFrame(layoutViewer);
    } else if (action === 'view-mode') {
      const view = viewerState();
      view.mode = button.dataset.mode;
      applyViewMode();
      requestAnimationFrame(layoutViewer);
    } else if (action === 'single-version') {
      const view = viewerState();
      view.single = button.dataset.versionKind;
      applyViewMode();
      requestAnimationFrame(layoutViewer);
    } else if (action === 'zoom') {
      zoomView(button.dataset.zoomAction);
    } else if (action === 'select-draft') {
      app.activeDraftId = id;
      renderDrafts();
    } else if (action === 'toggle-draft-expand') {
      app.draftExpanded = !app.draftExpanded;
      renderDrafts();
    } else if (action === 'copy-instruction') {
      const taskId = button.dataset.task;
      if (!app.instructions[taskId]) app.instructions[taskId] = await fetchText(`/api/instruction/${taskId}`);
      const ok = await copyText(app.instructions[taskId]);
      toast(ok ? '指令已复制；把它发给能访问本仓库的 AI。' : '复制失败，请手动选择下面的指令。', !ok);
      render();
    } else if (action === 'confirm-task') {
      await api('/api/ai/confirm', { method: 'POST', body: JSON.stringify({ taskId: button.dataset.task }) });
      toast('已确认；可以把指令复制给 AI。');
      await loadState();
    } else if (action === 'recreate-task') {
      await api('/api/ai/recreate', { method: 'POST', body: JSON.stringify({ taskId: button.dataset.task }) });
      toast('已生成新的 AI 任务版本；旧结果不会自动接入。');
      await loadState();
    } else if (action === 'enable-draft') {
      const draftId = id;
      const draft = draftById(draftId);
      const selected = app.draftSelected[draftId] || new Set();
      if (!draft || draft.status === 'enabled' || !(draft.items || []).length || !selected.size) {
        toast('没有勾选可启用的新增图片；先勾选至少一张。', true);
        return;
      }
      if (!window.confirm('启用后正式主页会切换；失败会自动恢复旧站点。确定启用？')) return;
      const data = await api(`/api/draft/${draftId}/enable`, {
        method: 'POST', body: JSON.stringify({ itemIds: [...selected] }),
      });
      toast(`已启用 ${data.publish.count} 张场景。`);
      await loadState();
    } else if (action === 'cancel-draft-items') {
      const draftId = id;
      const selected = app.draftSelected[draftId] || new Set();
      if (!selected.size) { toast('先勾选要从草稿里取消的图片。', true); return; }
      if (!window.confirm(`从草稿取消 ${selected.size} 张图片并重建草稿？正式主页不受影响。`)) return;
      await api(`/api/draft/${draftId}/cancel`, {
        method: 'POST', body: JSON.stringify({ itemIds: [...selected] }),
      });
      app.draftSelected[draftId] = new Set();
      toast('草稿已重建。');
      await loadState();
    }
  } catch (error) {
    toast(error.message, true);
  }
});

document.addEventListener('input', (event) => {
  if (event.target.type === 'range') {
    const output = event.target.closest('label')?.querySelector('output');
    if (output) output.textContent = `${Math.round(Number(event.target.value) * 100)}%`;
  }
});

document.addEventListener('change', async (event) => {
  if (event.target.matches('[data-select]')) {
    const id = event.target.dataset.select;
    if (event.target.checked) app.selected.add(id); else app.selected.delete(id);
    render();
  }
  if (event.target.matches('[data-draft-item]')) {
    const draftId = event.target.dataset.draftItem;
    const id = event.target.dataset.item;
    if (!app.draftSelected[draftId]) app.draftSelected[draftId] = new Set();
    if (event.target.checked) app.draftSelected[draftId].add(id);
    else app.draftSelected[draftId].delete(id);
    const draft = draftById(draftId);
    if (draft) syncDraftPreview(draft);
  }
  if (event.target.matches('[data-draft-select]')) {
    app.activeDraftId = event.target.value;
    renderDrafts();
  }
  if (event.target.matches('[data-time-for]')) {
    try {
      await api('/api/time', {
        method: 'POST',
        body: JSON.stringify({ itemId: event.target.dataset.timeFor, time: event.target.value }),
      });
      await loadState();
    } catch (error) {
      toast(error.message, true);
    }
  }
});

document.addEventListener('toggle', (event) => {
  const details = event.target.closest?.('details[data-key]');
  if (!details) return;
  if (details.open) app.openDetails.add(details.dataset.key);
  else app.openDetails.delete(details.dataset.key);
}, true);

document.addEventListener('pointerdown', (event) => {
  if (event.button !== 0) return;
  const frame = event.target.closest?.('[data-slider-frame]');
  if (frame) {
    if (isZoomed()) {
      if (event.target.closest('[data-slider-handle]')) beginSplitDrag(event, frame);
      else beginPan(event, frame);
    } else {
      beginSplitDrag(event, frame);
    }
    return;
  }
  const wrap = event.target.closest?.('[data-image-wrap]');
  if (wrap && isZoomed()) {
    const viewport = wrap.closest('[data-viewport]');
    if (viewport) beginPan(event, viewport);
  }
}, { passive: false });

document.addEventListener('keydown', (event) => {
  const handle = event.target.closest?.('[data-slider-handle]');
  if (!handle) return;
  const step = event.shiftKey ? 10 : 1;
  let value = Number(handle.getAttribute('aria-valuenow')) || 0;
  if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') value -= step;
  else if (event.key === 'ArrowRight' || event.key === 'ArrowUp') value += step;
  else if (event.key === 'Home') value = 0;
  else if (event.key === 'End') value = 100;
  else return;
  event.preventDefault();
  setSplit(value);
});

let resizeFrame = 0;
window.addEventListener('resize', () => {
  cancelAnimationFrame(resizeFrame);
  resizeFrame = requestAnimationFrame(() => {
    layoutWorkbench();
  });
});

if (document.fonts?.ready) {
  document.fonts.ready.then(() => layoutWorkbench());
}

document.getElementById('pick').addEventListener('click', () => document.getElementById('files').click());
document.getElementById('files').addEventListener('change', async (event) => {
  await uploadFiles(event.target.files);
  event.target.value = '';
});

const drop = document.getElementById('drop');
drop.addEventListener('dragover', (event) => {
  event.preventDefault();
  drop.classList.add('drag');
});
drop.addEventListener('dragleave', () => drop.classList.remove('drag'));
drop.addEventListener('drop', async (event) => {
  event.preventDefault();
  drop.classList.remove('drag');
  await uploadFiles(event.dataTransfer.files);
});

document.getElementById('start-delivered').addEventListener('click', () => {
  const ids = app.selected.size
    ? [...app.selected].filter((id) => ['received', 'previewed'].includes(itemById(id)?.status))
    : (app.data?.items || []).filter((item) => ['received', 'previewed'].includes(item.status)).map((item) => item.id);
  startItems(ids);
});

document.getElementById('scan-inbox').addEventListener('click', async () => {
  const status = document.getElementById('inbox-status');
  try {
    const data = await api('/api/scan-inbox', { method: 'POST', body: '{}' });
    status.textContent = `接收文件夹新发现 ${data.ingested.length} 张。`;
    status.classList.remove('error');
    await loadState();
  } catch (error) {
    status.textContent = error.message;
    status.classList.add('error');
  }
});

document.getElementById('start-all').addEventListener('click', () => {
  const ids = app.selected.size ? [...app.selected] : (app.data?.items || [])
    .filter((item) => ['received', 'previewed', 'planned', 'failed', 'cancelled'].includes(item.status))
    .map((item) => item.id);
  startItems(ids);
});

document.getElementById('refresh').addEventListener('click', async () => {
  try {
    const data = await api('/api/refresh', { method: 'POST', body: '{}' });
    toast(`刷新检查完成：${data.changes.length} 条 AI 回传变化。`);
    applyState(data.state);
  } catch (error) {
    toast(error.message, true);
  }
});

document.getElementById('scan-ai').addEventListener('click', async () => {
  try {
    const data = await api('/api/ai/scan', { method: 'POST', body: '{}' });
    const done = data.changes.filter((change) => change.status === 'done').length;
    const bad = data.changes.filter((change) => ['rejected', 'late', 'conflict'].includes(change.status)).length;
    toast(`AI 检查完成：接入 ${done} 张，拒绝或迟到 ${bad} 张。`, bad > 0);
    await loadState();
  } catch (error) {
    toast(error.message, true);
  }
});

document.getElementById('only-unadopted').addEventListener('change', (event) => {
  app.onlyUnadopted = event.target.checked;
  render();
});

document.getElementById('create-draft').addEventListener('click', async () => {
  const adopted = (app.data?.items || []).filter((item) => item.status === 'adopted');
  if (!adopted.length) { toast('先在“已处理”里采用一张图片，再加入草稿。', true); return; }
  try {
    const data = await api('/api/draft', {
      method: 'POST',
      body: JSON.stringify({
        name: `草稿 ${new Date().toLocaleString('zh-CN')}`,
        itemIds: adopted.map((item) => item.id),
      }),
    });
    toast(`草稿已建立：${data.draft.sceneCount} 张场景（含 54 张基线）。`);
    app.tab = 'drafts';
    await loadState();
  } catch (error) {
    toast(error.message, true);
  }
});

loadState().then(() => {
  startPolling();
  requestAnimationFrame(layoutWorkbench);
});
