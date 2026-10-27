// The creative workbench's page half: projects, references, GPT Image job packages,
// manual round trips, and isolated drafts. Everything shown here comes from the local
// creative state; the page never invents a generation percentage and never calls an
// image API. The gallery keeps its own tabs and its own state (app.js).
(() => {
  'use strict';

  const KIND_LABELS = {
    pointer: '鼠标图样', feather: '羽毛', bird: '青鸟', star: '星星／星芒', other: '其他',
  };
  const PROJECT_LABELS = {
    draft: '草稿', research: '调查中', 'reference-confirmed': '参考已确认',
    'awaiting-image': '等待回传', review: '待你检查', adopted: '已采用', archived: '已归档',
  };
  const JOB_LABELS = {
    waiting: '待交给 AI', done: '已回传', rejected: '回传被拒', late: '迟到结果',
    conflict: '结果冲突', cancelled: '已取消', superseded: '已替换',
  };
  const SOURCE_LABELS = {
    original: '初始版本', 'gpt-image': 'GPT Image', 'gpt-image-inpaint': 'GPT Image 补画',
    'manual-piskel': 'Piskel 手改', 'manual-krita': 'Krita 手改', generated: '生成',
  };
  const ROLE_LABELS = { full: '整图', shima: '岛村', adachi: '安达' };
  const EXPRESSION_LABELS = { open: '平时', shut: '闭眼', happy: '笑', squint: '眯眼' };
  const ALLOWED = ['colour', 'expression', 'shape', 'silhouette', 'canvas', 'paint'];
  const PRESERVED = ['silhouette', 'canvas', 'colour', 'expression', 'paint'];

  const state = {
    zone: 'library',
    data: null,
    project: null,
    projectId: null,
    busy: false,
    timer: 0,
    compare: null,
    detailRevision: null,
  };

  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[ch]));
  }

  function say(message, error = false) {
    const element = document.getElementById('creative-status');
    if (!element) return;
    element.textContent = message || '';
    element.classList.toggle('error', Boolean(error));
  }

  function label(map, key, fallback = '') {
    return map[key] || key || fallback;
  }

  async function call(path, options = {}) {
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

  async function upload(path, file, params) {
    const query = new URLSearchParams(params);
    const response = await fetch(`${path}?${query}`, {
      method: 'POST',
      headers: { 'Content-Type': file.type || 'application/octet-stream' },
      body: file,
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

  function formValues(form) {
    const result = {};
    for (const [key, value] of new FormData(form).entries()) {
      if (typeof value !== 'string') continue;
      if (Object.prototype.hasOwnProperty.call(result, key)) {
        result[key] = [].concat(result[key], value);
      } else {
        result[key] = value;
      }
    }
    return result;
  }

  function checked(form, name) {
    return [...form.querySelectorAll(`input[name="${name}"]:checked`)].map((item) => item.value);
  }

  function versionById(project, versionId) {
    return (project?.versions || []).find((version) => version.versionId === versionId) || null;
  }

  function referenceById(project, referenceId) {
    return (project?.references || []).find((reference) => reference.referenceId === referenceId) || null;
  }

  function versionImage(project, version) {
    if (!version) return '';
    if (version.previewPath && project?.versionPreviewUrls?.[version.versionId]) {
      return project.versionPreviewUrls[version.versionId];
    }
    return project?.versionUrls?.[version.versionId] || '';
  }

  function referenceImage(project, reference) {
    return project?.referenceUrls?.[reference.referenceId] || '';
  }

  function activeConfirmations(project) {
    return (project?.confirmations || []).filter((item) => item.status === 'active');
  }

  function gateLine(project) {
    const gate = project?.gate || {};
    if (!project?.references?.length) return '还没有参考；新对象制作前先加参考并确认。';
    if (gate.confirmed) return `参考已确认：${gate.activeConfirmationId || ''}`;
    if (gate.stale) return '参考已变化或确认未覆盖；请重新确认参考与修改范围。';
    return '参考尚未确认；确认后才能创建图像任务。';
  }

  function gateTag(project) {
    const gate = project?.gate || {};
    if (gate.confirmed) return '<span class="tag ok">参考已确认</span>';
    if (gate.stale) return '<span class="tag warn">待重新确认</span>';
    return '<span class="tag">参考待确认</span>';
  }

  function versionStrip(project) {
    const versions = project?.versions || [];
    const pointer = project?.objectKind === 'pointer';
    if (!versions.length) return `<p class="hint">还没有版本。${pointer ? '可以从现有指针图样建立初始版本。' : '先加本地图片参考，再从参考建立初始版本；之后才能做 edit / inpaint。'}</p>`;
    return `<div class="version-strip">${versions.map((version) => {
      const image = versionImage(project, version);
      const selected = project.selectedVersionId === version.versionId;
      return `<figure class="version-card${selected ? ' selected' : ''}">
        ${image ? `<div class="checker"><img src="${esc(image)}" alt="${esc(version.versionId)}" loading="lazy"></div>` : '<div class="checker empty">无预览</div>'}
        <figcaption>
          <span>${esc(version.versionId)}</span>
          <span>${esc(label(SOURCE_LABELS, version.source))} · ${version.size?.[0]}×${version.size?.[1]}</span>
          ${selected ? '<span class="tag ok">当前</span>' : `<button type="button" data-ca-action="adopt" data-version="${esc(version.versionId)}">采用</button>`}
        </figcaption>
      </figure>`;
    }).join('')}</div>`;
  }

  function confirmationList(project) {
    const confirmations = project?.confirmations || [];
    if (!confirmations.length) return '<p class="hint">还没有确认记录。</p>';
    return confirmations.map((confirmation) => `<article class="creative-row">
      <div>
        <strong>${esc(confirmation.confirmationId)}</strong>
        <span class="tag ${confirmation.status === 'active' ? 'ok' : 'warn'}">${confirmation.status === 'active' ? '有效' : '已失效'}</span>
        ${confirmation.staleReason ? `<span class="hint">${esc(confirmation.staleReason)}</span>` : ''}
      </div>
      <div class="hint">参考：${esc((confirmation.referenceIds || []).join('、'))}</div>
      <div class="hint">允许改：${esc((confirmation.scope?.allowedChanges || []).join('、') || '未填')}；保留：${esc((confirmation.scope?.preserved || []).join('、') || '未填')}</div>
      ${confirmation.note ? `<div class="hint">${esc(confirmation.note)}</div>` : ''}
    </article>`).join('');
  }

  function jobList(project) {
    const jobs = project?.jobs || [];
    if (!jobs.length) return '<p class="hint">还没有任务包。</p>';
    return jobs.map((job) => {
      const instruction = project?.jobInstructionUrls?.[job.jobId] || '';
      const result = job.resultPath ? `/creative-media/${job.resultPath}` : '';
      return `<article class="creative-row" data-job="${esc(job.jobId)}">
        <div class="creative-row-head">
          <strong>${esc(job.jobId)}</strong>
          <span class="tag ${job.status === 'done' ? 'ok' : job.status === 'waiting' ? 'blue' : 'warn'}">${esc(label(JOB_LABELS, job.status))}</span>
          <span class="tag">${esc(job.kind)} · ${esc(job.operation)}</span>
          ${job.paintedFill ? '<span class="tag warn">补画</span>' : ''}
        </div>
        <div class="hint">${esc(job.jobPath)} · revision ${esc(job.revision)}${job.inputSha256 ? ` · 输入 ${esc(job.inputSha256.slice(0, 10))}` : ''}</div>
        ${job.error ? `<p class="error">${esc(job.error)}</p>` : ''}
        ${result ? `<p class="hint">结果：<a class="link" href="${esc(result)}" target="_blank" rel="noopener">${esc(job.resultPath)}</a></p>` : ''}
        <div class="actions">
          ${instruction ? `<button type="button" data-ca-action="copy-instruction" data-job="${esc(job.jobId)}">复制指令</button>` : ''}
          ${instruction ? `<a class="tag" href="${esc(instruction)}" target="_blank" rel="noopener">打开指令 ↗</a>` : ''}
          ${['waiting', 'rejected'].includes(job.status) ? `<button type="button" data-ca-action="cancel-job" data-job="${esc(job.jobId)}">取消</button>` : ''}
          ${['rejected', 'late', 'conflict', 'cancelled'].includes(job.status) ? `<button type="button" data-ca-action="rebuild-job" data-job="${esc(job.jobId)}">重建任务</button>` : ''}
        </div>
      </article>`;
    }).join('');
  }

  function previewList(project) {
    const previews = project?.previews || [];
    if (!previews.length) return '<p class="hint">还没有制作草稿。选一个版本建草稿，只在隔离路径里查看。</p>';
    return previews.map((preview) => `<article class="creative-row">
      <div class="creative-row-head">
        <strong>${esc(preview.previewId)}</strong>
        <span class="tag ${preview.status === 'ready' ? 'ok' : preview.status === 'stale' ? 'warn' : 'blue'}">${esc(preview.status)}</span>
        <span class="tag">${esc(preview.versionId)}</span>
      </div>
      <div class="hint">覆盖：${esc((preview.overlay || []).join('、'))}</div>
      ${(preview.mismatches || []).length ? `<p class="error">${esc((preview.mismatches || []).map((item) => `${item.path}: ${item.kind}`).join('；'))}</p>` : ''}
      <div class="actions">
        <a class="tag" href="${esc(project?.previewUrls?.[preview.previewId] || '')}" target="_blank" rel="noopener">打开隔离预览 ↗</a>
        <button type="button" data-ca-action="check-preview" data-preview="${esc(preview.previewId)}">检查基线</button>
        ${preview.status !== 'applied' ? `<button type="button" data-ca-action="apply-preview" data-preview="${esc(preview.previewId)}">应用草稿</button>` : `<button type="button" data-ca-action="rollback-preview" data-preview="${esc(preview.previewId)}">回滚</button>`}
      </div>
    </article>`).join('');
  }

  function manualList(project) {
    const exports = project?.manualExports || [];
    if (!exports.length) return '<p class="hint">还没有手改导出。</p>';
    return exports.map((item) => {
      const files = (item.files || []).map((file) => `<a class="tag" href="/creative-media/${esc(item.path)}/${esc(file)}" target="_blank" rel="noopener">${esc(file)} ↗</a>`).join(' ');
      return `<article class="creative-row"><div class="creative-row-head"><strong>${esc(item.exportId)}</strong><span class="tag">${esc(item.versionId)}</span></div><div class="hint">${esc(item.role || 'full')} · ${esc(item.expression || 'open')} · ${esc(item.editor || 'piskel')}</div><div class="actions">${files}</div></article>`;
    }).join('');
  }

  function localReferenceOptions(project) {
    return (project?.references || []).filter((reference) =>
      (reference.kind === 'image' || reference.kind === 'film-frame') && reference.path)
      .map((reference) => `<option value="${esc(reference.referenceId)}">${esc(reference.title || reference.referenceId)} · ${reference.size?.[0]}×${reference.size?.[1]}</option>`).join('');
  }

  function defaultVersionId(project) {
    if (!project?.versions?.length) return '';
    if (project.selectedVersionId) return project.selectedVersionId;
    return project.versions[project.versions.length - 1].versionId;
  }

  function versionOptions(project, chosen = defaultVersionId(project)) {
    return (project?.versions || []).map((version) =>
      `<option value="${esc(version.versionId)}"${version.versionId === chosen ? ' selected' : ''}>${esc(version.versionId)} · ${esc(label(SOURCE_LABELS, version.source))} · ${version.size?.[0]}×${version.size?.[1]}</option>`).join('');
  }

  function referenceChecks(project) {
    return (project?.references || []).map((reference) =>
      `<label class="check"><input type="checkbox" name="referenceIds" value="${esc(reference.referenceId)}"> ${esc(reference.title || reference.referenceId)}</label>`).join('');
  }

  function allowedChecks(name, values, selected = []) {
    return values.map((value) =>
      `<label class="check"><input type="checkbox" name="${esc(name)}" value="${esc(value)}"${selected.includes(value) ? ' checked' : ''}> ${esc(value)}</label>`).join('');
  }

  function detailHtml(project) {
    const kind = project.objectKind;
    const selected = versionById(project, project.selectedVersionId);
    const compare = versionById(project, state.compare);
    const pointer = kind === 'pointer';
    const gateOpen = Boolean(project?.gate?.confirmed);
    return `<div class="creative-head">
      <div>
        <h2>${esc(project.name)}</h2>
        <p class="hint">${esc(project.projectId)} · ${esc(label(KIND_LABELS, kind))} · ${esc(label(PROJECT_LABELS, project.status))} · revision ${esc(project.revision)}</p>
        <p class="hint">${esc(project.purpose || '未填写用途')}</p>
      </div>
      <div class="actions">
        <button type="button" data-ca-action="refresh-project">刷新项目</button>
        <button type="button" data-ca-action="archive-project">归档</button>
      </div>
    </div>
    <div class="creative-gate">${gateTag(project)}<span class="hint">${esc(gateLine(project))}</span></div>
    ${(project.issues || []).length ? `<div class="creative-issues">${(project.issues || []).map((item) => `<p class="error">${esc(item.message || item.kind)}</p>`).join('')}</div>` : ''}

    <div class="creative-columns">
      <section class="creative-section">
        <h3>参考与确认</h3>
        <div class="creative-refs">${referenceCards(project)}</div>
        <form class="settings creative-form" data-ca-form="reference-file" data-project="${esc(project.projectId)}">
          <h3>加参考图片</h3>
          <label>文件 <input type="file" name="file" accept="image/*" required></label>
          <label>标题 <input name="title" maxlength="120" placeholder="官方插画、电影帧…"></label>
          <label>来源链接 <input name="uri" maxlength="400" placeholder="https://…"></label>
          <label>时间码 <input name="timecode" maxlength="40" placeholder="00:43:30"></label>
          <label>调查结论 <textarea name="findings" rows="2" placeholder="形态、配色、可见细节"></textarea></label>
          <label>不确定处 <textarea name="uncertainties" rows="2" placeholder="每行一条"></textarea></label>
          <div class="actions"><button type="submit" class="primary">加参考</button></div>
        </form>
        <form class="settings creative-form" data-ca-form="reference-link" data-project="${esc(project.projectId)}">
          <h3>加参考链接</h3>
          <label>标题 <input name="title" required maxlength="120"></label>
          <label>链接 <input name="uri" required maxlength="600" placeholder="https://…"></label>
          <label>时间码 <input name="timecode" maxlength="40"></label>
          <label>说明 <textarea name="note" rows="2"></textarea></label>
          <div class="actions"><button type="submit">加链接</button></div>
        </form>
        <form class="settings creative-form" data-ca-form="confirm" data-project="${esc(project.projectId)}">
          <h3>确认参考与修改范围</h3>
          <p class="hint">只有你能确认。执行 AI 或研究任务不能代替这一步。</p>
          <div class="creative-checks">${referenceChecks(project)}</div>
          <fieldset><legend>允许改</legend>${allowedChecks('allowedChanges', ALLOWED)}</fieldset>
          <fieldset><legend>保留</legend>${allowedChecks('preserved', PRESERVED)}</fieldset>
          <label>说明 <input name="note" maxlength="300" placeholder="本次确认的修改范围"></label>
          <div class="actions"><button type="submit" class="primary">确认这些参考</button></div>
        </form>
        <div class="creative-subhead"><h3>确认记录</h3>${confirmationList(project)}</div>
      </section>

      <section class="creative-section">
        <h3>任务包</h3>
        <div class="actions">
          <button type="button" data-ca-action="scan">扫描回传</button>
        </div>
        <form class="settings creative-form" data-ca-form="job" data-project="${esc(project.projectId)}">
          <h3>新建任务</h3>
          <p class="hint" data-ca-job-gate>${gateOpen ? '' : '参考未确认或已过期：图像与动效任务已禁用；请先确认参考。'}</p>
          <fieldset class="creative-job-fields"${gateOpen ? '' : ' disabled'}>
          <label>类型
            <select name="kind">
              <option value="image">GPT Image 图像</option>
              <option value="research">参考调查</option>
              <option value="motion">动效说明</option>
            </select>
          </label>
          <label>操作
            <select name="operation">
              <option value="edit">按输入修改</option>
              <option value="inpaint">补画</option>
              <option value="generate">从参考生成</option>
              <option value="research">调查</option>
              <option value="motion">动效</option>
            </select>
          </label>
          <label>输入版本 <select name="inputVersionId"><option value=""${defaultVersionId(project) ? '' : ' selected'}>无（从参考生成）</option>${versionOptions(project)}</select></label>
          <div class="creative-checks">${referenceChecks(project)}</div>
          <fieldset><legend>允许改</legend>${allowedChecks('allowedChanges', ALLOWED)}</fieldset>
          <fieldset><legend>保留</legend>${allowedChecks('preserved', PRESERVED)}</fieldset>
          <label>输出宽 <input type="number" name="width" min="1" value="${pointer ? 46 : kind === 'feather' ? 350 : ''}" placeholder="46"></label>
          <label>输出高 <input type="number" name="height" min="1" value="${pointer ? 27 : kind === 'feather' ? 512 : ''}" placeholder="27"></label>
          <label class="check"><input type="checkbox" name="requireAlpha" checked> 必须保留透明通道</label>
          <label class="check"><input type="checkbox" name="paintedFill"> 这是补画（不伪装成电影可见证据）</label>
          <div class="actions"><button type="submit" class="primary"${gateOpen ? '' : ' disabled'}>生成任务包</button></div>
          </fieldset>
        </form>
        <div class="creative-jobs">${jobList(project)}</div>
      </section>
    </div>

    <div class="creative-columns">
      <section class="creative-section">
        <h3>版本</h3>
        ${versionStrip(project)}
        ${selected ? `<div class="creative-compare">
          <div class="checker"><img src="${esc(versionImage(project, selected))}" alt="当前版本 ${esc(selected.versionId)}"></div>
          <div class="hint">当前：${esc(selected.versionId)} · ${esc(label(SOURCE_LABELS, selected.source))} · ${selected.size?.[0]}×${selected.size?.[1]} · ${esc(selected.format || '')}</div>
        </div>` : ''}
        ${compare ? `<div class="creative-compare">
          <div class="checker"><img src="${esc(versionImage(project, compare))}" alt="对照版本 ${esc(compare.versionId)}"></div>
          <div class="hint">对照：${esc(compare.versionId)} · ${esc(label(SOURCE_LABELS, compare.source))} · ${compare.size?.[0]}×${compare.size?.[1]}</div>
        </div>` : ''}
        <div class="actions">
          ${(project.versions || []).map((version) => `<button type="button" data-ca-action="compare" data-version="${esc(version.versionId)}">对照 ${esc(version.versionId)}</button>`).join('')}
          ${pointer ? '<button type="button" data-ca-action="seed-pointer">从现有指针图样建立初始版本</button>' : ''}
        </div>
        ${!pointer ? (localReferenceOptions(project) ? `<form class="settings creative-form" data-ca-form="seed" data-project="${esc(project.projectId)}">
          <h3>从参考建立初始版本</h3>
          <p class="hint">先确认参考；初始版本之后才能做 inpaint / edit 和手改。不会替换正式图样。</p>
          <label>参考 <select name="referenceId">${localReferenceOptions(project)}</select></label>
          <div class="actions"><button type="submit" class="primary">建立初始版本</button></div>
        </form>` : '<p class="hint">先加本地图片参考，才能建立初始版本。</p>') : ''}
        <form class="settings creative-form" data-ca-form="export" data-project="${esc(project.projectId)}">
          <h3>手改导出</h3>
          <label>版本 <select name="versionId">${versionOptions(project)}</select></label>
          <label>角色 <select name="role"><option value="full">整图</option><option value="shima">岛村</option><option value="adachi">安达</option></select></label>
          <label>表情 <select name="expression"><option value="open">平时</option><option value="shut">闭眼</option><option value="happy">笑</option><option value="squint">眯眼</option></select></label>
          <label>编辑器 <select name="editor"><option value="piskel">Piskel</option><option value="krita">Krita</option></select></label>
          <div class="actions"><button type="submit" class="primary">导出 PNG / 工程</button></div>
        </form>
        <form class="settings creative-form" data-ca-form="import" data-project="${esc(project.projectId)}">
          <h3>导入手改</h3>
          <p class="hint">PNG 或 .piskel 必须与父版本同尺寸；不会自动拉伸。导出的未改文件原样导入应逐像素一致。</p>
          <label>父版本 <select name="parentVersionId">${versionOptions(project)}</select></label>
          <label>角色 <select name="role"><option value="full">整图</option><option value="shima">岛村</option><option value="adachi">安达</option></select></label>
          <label>表情 <select name="expression"><option value="open">平时</option><option value="shut">闭眼</option><option value="happy">笑</option><option value="squint">眯眼</option></select></label>
          <label>编辑器 <select name="editor"><option value="piskel">Piskel</option><option value="krita">Krita</option></select></label>
          <label>文件 <input type="file" name="file" accept="image/png,.piskel,application/json" required></label>
          <label>说明 <input name="note" maxlength="300"></label>
          <div class="actions"><button type="submit" class="primary">导入手改</button></div>
        </form>
        <div class="creative-subhead"><h3>手改记录</h3>${manualList(project)}</div>
      </section>

      <section class="creative-section">
        <h3>制作草稿</h3>
        <form class="settings creative-form" data-ca-form="preview" data-project="${esc(project.projectId)}">
          <h3>建立隔离草稿</h3>
          <label>版本 <select name="versionId">${versionOptions(project)}</select></label>
          <label>名称 <input name="name" maxlength="80" placeholder="草稿名称"></label>
          <label>额外覆盖 <input name="overlays" maxlength="400" placeholder="仅星星/其他对象：site 相对路径，逗号分隔"></label>
          <div class="actions"><button type="submit" class="primary">建立草稿</button></div>
        </form>
        <div class="creative-previews">${previewList(project)}</div>
      </section>
    </div>`;
  }

  function referenceCards(project) {
    const references = project?.references || [];
    if (!references.length) return '<p class="hint">还没有参考。调查后把原图、电影帧或链接加进来。</p>';
    return references.map((reference) => {
      const image = referenceImage(project, reference);
      return `<article class="creative-ref">
        ${image ? `<div class="checker"><img src="${esc(image)}" alt="${esc(reference.title || reference.referenceId)}" loading="lazy"></div>` : '<div class="checker empty">链接参考</div>'}
        <div class="creative-ref-body">
          <strong>${esc(reference.title || reference.referenceId)}</strong>
          <span class="id">${esc(reference.referenceId)} · revision ${esc(reference.revision)}</span>
          ${reference.source?.uri ? `<span class="hint">${esc(reference.source.uri)}${reference.source.timecode ? ` · ${esc(reference.source.timecode)}` : ''}</span>` : ''}
          ${reference.source?.note ? `<span class="hint">${esc(reference.source.note)}</span>` : ''}
          ${reference.findings ? `<p class="hint">${esc(reference.findings)}</p>` : ''}
          ${(reference.uncertainties || []).length ? `<p class="hint">不确定：${esc((reference.uncertainties || []).join('；'))}</p>` : ''}
          ${reference.missing ? '<span class="tag warn">文件缺失</span>' : ''}
        </div>
      </article>`;
    }).join('');
  }

  function renderList() {
    const list = document.getElementById('creative-list');
    const count = document.getElementById('creative-count');
    const projects = state.data?.projects || [];
    if (count) count.textContent = projects.length ? String(projects.length) : '';
    if (!list) return;
    if (!projects.length) { list.innerHTML = '<p class="hint">还没有制作项目。</p>'; return; }
    list.innerHTML = projects.map((project) => `<button type="button" class="creative-item${project.projectId === state.projectId ? ' active' : ''}" data-ca-action="select-project" data-project="${esc(project.projectId)}">
      <span class="creative-item-name">${esc(project.name)}</span>
      <span class="creative-item-meta">${esc(label(KIND_LABELS, project.objectKind))} · ${esc(label(PROJECT_LABELS, project.status))}</span>
      <span class="creative-item-meta">${project.counts?.references || 0} 参考 · ${project.counts?.versions || 0} 版本 · ${project.counts?.jobsWaiting || 0} 待回传</span>
      <span class="creative-item-meta">${project.gate?.confirmed ? '参考已确认' : project.gate?.stale ? '待重新确认' : '参考待确认'}</span>
    </button>`).join('');
  }

  function renderDetail() {
    const detail = document.getElementById('creative-detail');
    if (!detail) return;
    if (!state.project) {
      detail.innerHTML = '<p class="hint">在左侧选择或新建一个项目。</p>';
      return;
    }
    detail.innerHTML = detailHtml(state.project);
  }

  function render() {
    document.querySelectorAll('[data-zone]').forEach((button) => {
      button.setAttribute('aria-pressed', String(button.dataset.zone === state.zone));
    });
    const library = document.getElementById('zone-library');
    const creative = document.getElementById('zone-creative');
    if (library) library.hidden = state.zone !== 'library';
    if (creative) creative.hidden = state.zone !== 'creative';
    renderList();
    renderDetail();
  }

  async function loadState() {
    try {
      state.data = await call('/api/creative/state');
      if (state.projectId && !(state.data.projects || []).some((project) => project.projectId === state.projectId)) {
        state.projectId = null;
        state.project = null;
      }
      if (state.projectId) await loadProject(state.projectId);
      else render();
    } catch (error) {
      say(`制作区状态读取失败：${error.message}`, true);
    }
  }

  async function loadProject(projectId) {
    try {
      const data = await call(`/api/creative/project/${encodeURIComponent(projectId)}`);
      state.project = data.project;
      state.projectId = projectId;
      state.detailRevision = state.project.revision;
      if (!state.compare || !versionById(state.project, state.compare)) state.compare = null;
      render();
    } catch (error) {
      say(`项目读取失败：${error.message}`, true);
    }
  }

  async function act(action, button) {
    const project = state.project;
    const projectId = state.projectId;
    const versionId = button?.dataset?.version || '';
    const previewId = button?.dataset?.preview || '';
    const jobId = button?.dataset?.job || '';
    if (action === 'refresh') { await loadState(); return; }
    if (action === 'refresh-project') { if (projectId) await loadProject(projectId); return; }
    if (action === 'select-project') {
      state.projectId = button.dataset.project;
      state.compare = null;
      await loadProject(state.projectId);
      return;
    }
    if (action === 'archive-project') {
      if (!projectId || !window.confirm('归档项目？归档后不能创建新任务。')) return;
      await call('/api/creative/project/archive', { method: 'POST', body: JSON.stringify({ projectId }) });
      say('项目已归档。');
      await loadProject(projectId);
      return;
    }
    if (action === 'adopt') {
      await call('/api/creative/adopt', { method: 'POST', body: JSON.stringify({ projectId, versionId }) });
      say(`已采用 ${versionId}。`);
      await loadProject(projectId);
      return;
    }
    if (action === 'compare') {
      state.compare = versionId;
      renderDetail();
      return;
    }
    if (action === 'seed-pointer') {
      await call('/api/creative/pointer/seed', { method: 'POST', body: JSON.stringify({ projectId }) });
      say('已从现有指针图样建立初始版本。');
      await loadProject(projectId);
      return;
    }
    if (action === 'scan') {
      const data = await call('/api/creative/jobs/scan', { method: 'POST', body: JSON.stringify({ projectId }) });
      say(`扫描完成：${(data.changes || []).length} 条变化。`);
      await loadProject(projectId);
      return;
    }
    if (action === 'cancel-job') {
      await call('/api/creative/job/cancel', { method: 'POST', body: JSON.stringify({ projectId, jobId }) });
      say('任务已取消；迟到结果不会接入当前版本。');
      await loadProject(projectId);
      return;
    }
    if (action === 'rebuild-job') {
      await call('/api/creative/job/rebuild', { method: 'POST', body: JSON.stringify({ projectId, jobId }) });
      say('已生成新的任务版本；旧任务保留在任务目录。');
      await loadProject(projectId);
      return;
    }
    if (action === 'copy-instruction') {
      const url = project?.jobInstructionUrls?.[jobId];
      if (!url) { say('没有指令地址。', true); return; }
      const response = await fetch(url);
      const text = await response.text();
      if (!response.ok) { say(text || '指令读取失败。', true); return; }
      try {
        await navigator.clipboard.writeText(text);
        say('指令已复制；把它交给具备 GPT Image 工具的执行 AI。');
      } catch {
        window.prompt('复制下面的指令：', text);
      }
      return;
    }
    if (action === 'check-preview') {
      const data = await call('/api/creative/preview/check', { method: 'POST', body: JSON.stringify({ projectId, previewId }) });
      say(`草稿状态：${data.preview.status}。`);
      await loadProject(projectId);
      return;
    }
    if (action === 'apply-preview') {
      if (!window.confirm('应用草稿会写入正式 site 的 allowlist 文件；先确认已看预览。继续？')) return;
      const data = await call('/api/creative/preview/apply', { method: 'POST', body: JSON.stringify({ projectId, previewId, confirm: true }) });
      say(`草稿已应用：${data.preview.status}。`);
      await loadProject(projectId);
      return;
    }
    if (action === 'rollback-preview') {
      if (!window.confirm('回滚会用备份恢复正式 site 的 allowlist 文件。继续？')) return;
      const data = await call('/api/creative/preview/rollback', { method: 'POST', body: JSON.stringify({ projectId, previewId }) });
      say(`草稿已回滚：${data.preview.status}。`);
      await loadProject(projectId);
      return;
    }
  }

  async function submit(form) {
    const name = form.dataset.caForm;
    const projectId = form.dataset.project || state.projectId;
    const values = formValues(form);
    if (name === 'reference-file') {
      const file = form.querySelector('input[type="file"]')?.files?.[0];
      if (!file) { say('先选择参考图片。', true); return; }
      const data = await upload('/api/creative/reference/file', file, {
        projectId, name: file.name, title: values.title || file.name,
        kind: 'image', timecode: values.timecode || '', note: values.uri || '',
        findings: values.findings || '', uncertainties: values.uncertainties || '',
      });
      say(`参考已加入：${data.reference.referenceId}。`);
    } else if (name === 'reference-link') {
      await call('/api/creative/reference/link', { method: 'POST', body: JSON.stringify({
        projectId, title: values.title, uri: values.uri, kind: 'link',
        timecode: values.timecode || '', note: values.note || '',
        findings: values.findings || '', uncertainties: values.uncertainties || '',
      }) });
      say('参考链接已加入。');
    } else if (name === 'confirm') {
      await call('/api/creative/reference/confirm', { method: 'POST', body: JSON.stringify({
        projectId, referenceIds: checked(form, 'referenceIds'),
        allowedChanges: checked(form, 'allowedChanges'), preserved: checked(form, 'preserved'),
        note: values.note || '',
      }) });
      say('参考已确认；现在可以创建图像任务。');
    } else if (name === 'job') {
      if (values.kind !== 'research' && !state.project?.gate?.confirmed) {
        say('参考未确认或已过期；请先确认参考。', true);
        return;
      }
      const width = Number(values.width);
      const height = Number(values.height);
      const outputSize = Number.isInteger(width) && Number.isInteger(height) && width > 0 && height > 0
        ? [width, height] : null;
      const data = await call('/api/creative/job', { method: 'POST', body: JSON.stringify({
        projectId, kind: values.kind, operation: values.operation,
        inputVersionId: values.inputVersionId || null,
        referenceIds: checked(form, 'referenceIds'),
        allowedChanges: checked(form, 'allowedChanges'), preserved: checked(form, 'preserved'),
        outputSize, requireAlpha: form.querySelector('[name="requireAlpha"]')?.checked ?? true,
        paintedFill: form.querySelector('[name="paintedFill"]')?.checked ?? false,
      }) });
      say(`任务包已生成：${data.job.jobId}。复制指令交给具备 GPT Image 工具的执行 AI。`);
    } else if (name === 'seed') {
      const data = await call('/api/creative/seed', { method: 'POST', body: JSON.stringify({
        projectId, referenceId: values.referenceId,
      }) });
      say(`已从参考建立初始版本：${data.version.versionId}。`);
    } else if (name === 'export') {
      const data = await call('/api/creative/manual/export', { method: 'POST', body: JSON.stringify({
        projectId, versionId: values.versionId, role: values.role,
        expression: values.expression, editor: values.editor,
      }) });
      say(`手改导出已生成：${data.export.exportId}。`);
    } else if (name === 'import') {
      const file = form.querySelector('input[type="file"]')?.files?.[0];
      if (!file) { say('先选择 PNG 或 .piskel 文件。', true); return; }
      if (file.name.toLowerCase().endsWith('.piskel')) {
        const text = await file.text();
        const data = await call('/api/creative/manual/import-piskel', { method: 'POST', body: JSON.stringify({
          projectId, parentVersionId: values.parentVersionId, role: values.role,
          expression: values.expression, editor: values.editor, note: values.note || '',
          piskel: JSON.parse(text),
        }) });
        say(`手改已导入：${data.version.versionId}。`);
      } else {
        const data = await upload('/api/creative/manual/import', file, {
          projectId, parentVersionId: values.parentVersionId, role: values.role,
          expression: values.expression, editor: values.editor, note: values.note || '',
        });
        say(`手改已导入：${data.version.versionId}。`);
      }
    } else if (name === 'preview') {
      const overlays = String(values.overlays || '').split(',').map((item) => item.trim()).filter(Boolean);
      const data = await call('/api/creative/preview', { method: 'POST', body: JSON.stringify({
        projectId, versionId: values.versionId, name: values.name || '',
        overlays,
      }) });
      say(`草稿已建立：${data.preview.previewId}。`);
    }
    await loadProject(projectId);
  }

  document.addEventListener('click', async (event) => {
    const zone = event.target.closest('[data-zone]');
    if (zone) {
      state.zone = zone.dataset.zone;
      render();
      if (state.zone === 'creative') await loadState();
      return;
    }
    const button = event.target.closest('[data-ca-action]');
    if (!button) return;
    try {
      await act(button.dataset.caAction, button);
    } catch (error) {
      say(error.message, true);
    }
  });

  document.addEventListener('submit', async (event) => {
    const form = event.target.closest('[data-ca-form], #creative-create');
    if (!form) return;
    event.preventDefault();
    try {
      if (form.id === 'creative-create') {
        const values = formValues(form);
        const data = await call('/api/creative/project', { method: 'POST', body: JSON.stringify({
          name: values.name, objectKind: values.objectKind, purpose: values.purpose || '',
        }) });
        form.reset();
        document.getElementById('creative-create-status').textContent = '项目已建立。';
        state.projectId = data.project.projectId;
        await loadState();
        return;
      }
      await submit(form);
    } catch (error) {
      const status = form.querySelector('.drop-status') || document.getElementById('creative-create-status');
      if (status) { status.textContent = error.message; status.classList.add('error'); }
      say(error.message, true);
    }
  });

  document.addEventListener('change', async (event) => {
    const input = event.target.closest('input[type="file"]');
    if (!input) return;
    if (input.closest('[data-ca-form="import"]')) {
      const form = input.closest('form');
      try { await submit(form); } catch (error) { say(error.message, true); }
    }
  });

  function startPolling() {
    clearInterval(state.timer);
    state.timer = setInterval(async () => {
      if (state.zone !== 'creative' || state.busy) return;
      try {
        const data = await call('/api/creative/state');
        state.data = data;
        if (state.projectId) {
          const summary = (data.projects || []).find((project) => project.projectId === state.projectId);
          if (!summary) { state.projectId = null; state.project = null; }
          else if (summary.revision !== state.detailRevision) await loadProject(state.projectId);
        }
        render();
      } catch {
        // A transient poll failure is reported by the next user action.
      }
    }, 3000);
  }

  loadState().then(startPolling);
})();
