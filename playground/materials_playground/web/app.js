const sessionsEl = document.getElementById('sessions');
const messagesEl = document.getElementById('messages');
const trajectoryEl = document.getElementById('trajectory');
const logsEl = document.getElementById('logs');
const metaEl = document.getElementById('sessionMeta');
const inputEl = document.getElementById('messageInput');
const workspaceTreeEl = document.getElementById('workspaceTree');
const fileEditorEl = document.getElementById('fileEditor');
const currentPathEl = document.getElementById('currentPath');
const imagePreviewEl = document.getElementById('imagePreview');
const imagePreviewImgEl = document.getElementById('imagePreviewEl');
const artifactSummaryEl = document.getElementById('artifactSummary');
const modelSelectEl = document.getElementById('modelSelect');
const contextGaugeEl = document.getElementById('contextGauge');
const contextGaugeValueEl = document.getElementById('contextGaugeValue');
const contextGaugePctEl = document.getElementById('contextGaugePct');
const apiTokenCostEl = document.getElementById('apiTokenCost');
const messageAttachmentsEl = document.getElementById('messageAttachments');
const tabButtons = Array.from(document.querySelectorAll('.tab-btn'));
const tabContents = Array.from(document.querySelectorAll('.tab-content'));

let activeSessionId = null;
let activeFilePath = null;
let currentWorkspacePath = '';
let sessionStream = null;
let sessionRefreshTimer = null;
let activeTab = 'messages';
let lastFlowSignature = '';
let lastMetaSignature = '';
let streamSessionId = null;
let latestRenderState = { flow: [], finish: null };
const DEFAULT_CONTEXT_LIMIT_TOKENS = 128000;
const stagedUploads = [];
const pendingMessageImages = [];
const pendingMessageImageKeys = new Set();
let lastPasteSignature = '';
let lastPasteHandledAt = 0;

function debugLog(...args) {
  // Keep a unified console prefix for quickly locating UI runtime errors.
  console.error('[materials-web]', ...args);
}

function escapeHtml(value) {
  return String(value || '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
}

function summarizeStatus(status) {
  const map = {
    completed: '完成',
    failed: '失败',
    running: '进行中',
    cancelling: '终止中',
    cancelled: '已终止',
    pending: '等待中',
    success: '完成',
    idle: '空闲',
    retrying_llm: '重试中',
    requesting_llm: '请求模型',
  };
  return map[status] || status || '未知';
}

function setStatusToast(text, tone = 'info') {
  let bar = document.getElementById('statusToast');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'statusToast';
    bar.className = 'status-toast';
    document.body.appendChild(bar);
  }
  bar.textContent = text;
  bar.dataset.tone = tone;
  bar.classList.add('show');
  setTimeout(() => bar.classList.remove('show'), 1600);
}

async function requestJson(url, options = {}) {
  const res = await fetch(url, options);
  let data = null;
  try {
    data = await res.json();
  } catch (_) {
    data = null;
  }
  if (!res.ok) {
    const err = new Error((data && (data.error || data.message)) || `HTTP_${res.status}`);
    err.status = res.status;
    err.payload = data;
    throw err;
  }
  return data || {};
}

function setBusy(buttonEl, busy, busyText = '处理中...') {
  if (!buttonEl) return;
  if (busy) {
    if (!buttonEl.dataset.idleText) buttonEl.dataset.idleText = buttonEl.textContent || '';
    buttonEl.disabled = true;
    buttonEl.textContent = busyText;
    return;
  }
  buttonEl.disabled = false;
  if (buttonEl.dataset.idleText) buttonEl.textContent = buttonEl.dataset.idleText;
}

function updateUploadButtonLabel() {
  const uploadBtn = document.getElementById('uploadFileBtn');
  if (!uploadBtn) return;
  const count = stagedUploads.length;
  uploadBtn.textContent = count > 0 ? `上传文件（缓存 ${count}）` : '上传文件';
}

function renderMessageAttachments() {
  if (!messageAttachmentsEl) return;
  if (!pendingMessageImages.length) {
    messageAttachmentsEl.textContent = '';
    return;
  }
  messageAttachmentsEl.textContent = `待发送图片: ${pendingMessageImages.map((x) => x.name).join(', ')}`;
}

function buildImageKey(dataUrl, name = '') {
  const value = String(dataUrl || '').trim();
  if (!value) return '';
  const head = value.slice(0, 80);
  const tail = value.slice(-80);
  return `${String(name || '').trim()}|${value.length}|${head}|${tail}`;
}

function appendPendingMessageImage(name, dataUrl) {
  const normalizedDataUrl = String(dataUrl || '').trim();
  if (!normalizedDataUrl) return false;
  const key = buildImageKey(normalizedDataUrl, name);
  if (!key || pendingMessageImageKeys.has(key)) return false;
  pendingMessageImageKeys.add(key);
  pendingMessageImages.push({ name: String(name || 'image').trim() || 'image', dataUrl: normalizedDataUrl });
  return true;
}

function stripImagePlaceholders(text) {
  return String(text || '')
    .replace(/!\[[^\]]*\]\([^)]+\)/g, ' ')
    .replace(/<img\b[^>]*>/gi, ' ')
    .replace(/\[(?:image|img|图片)\]/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function buildOutgoingMessagePayload(text) {
  const cleanedText = String(text || '').trim();
  if (!pendingMessageImages.length) return cleanedText;
  const normalizedText = stripImagePlaceholders(cleanedText);
  const blocks = [];
  if (normalizedText) {
    blocks.push({ type: 'text', text: normalizedText });
  }
  for (const img of pendingMessageImages) {
    blocks.push({
      type: 'image_url',
      image_url: { url: img.dataUrl }
    });
  }
  if (!blocks.length) {
    blocks.push({ type: 'text', text: '请分析附加图片内容' });
  }
  return blocks;
}

function clearPendingMessageImages() {
  pendingMessageImageKeys.clear();
  pendingMessageImages.splice(0, pendingMessageImages.length);
  renderMessageAttachments();
}

function isPreviewImage(path) {
  return /\.png$/i.test(String(path || ''));
}

function setEditorMode(mode, path = '') {
  const saveBtn = document.getElementById('saveFileBtn');
  if (mode === 'image') {
    fileEditorEl.classList.add('hidden');
    imagePreviewEl.classList.remove('hidden');
    imagePreviewImgEl.src = `/api/workspace/raw?session_id=${encodeURIComponent(activeSessionId)}&path=${encodeURIComponent(path)}`;
    imagePreviewImgEl.alt = path || 'PNG 预览';
    fileEditorEl.value = '';
    if (saveBtn) saveBtn.disabled = true;
    return;
  }
  imagePreviewEl.classList.add('hidden');
  imagePreviewImgEl.removeAttribute('src');
  fileEditorEl.classList.remove('hidden');
  if (saveBtn) saveBtn.disabled = false;
}

function formatInteger(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n) || n < 0) return '0';
  return Math.round(n).toLocaleString('en-US');
}

const ESTIMATED_TOKENS_PER_IMAGE_BLOCK = 512;

function normalizeContextSegments(content) {
  const textChunks = [];
  let imageBlocks = 0;

  const pushText = (value) => {
    const text = String(value || '').trim();
    if (text) textChunks.push(text);
  };

  if (content == null) return { textChunks, imageBlocks };
  if (typeof content === 'string') return { textChunks: content.trim() ? [content.trim()] : [], imageBlocks };

  if (Array.isArray(content)) {
    content.forEach((block) => {
      if (typeof block === 'string') {
        pushText(block);
        return;
      }
      if (!block || typeof block !== 'object') {
        pushText(block);
        return;
      }
      if (block.type === 'text') {
        pushText(block.text);
        return;
      }
      if (block.type === 'image_url') {
        imageBlocks += 1;
        return;
      }
      pushText(JSON.stringify(block));
    });
    return { textChunks, imageBlocks };
  }

  if (typeof content === 'object') {
    pushText(JSON.stringify(content));
    return { textChunks, imageBlocks };
  }

  pushText(content);
  return { textChunks, imageBlocks };
}

function estimateContextTokens(contextSegments) {
  const text = ((contextSegments && contextSegments.textChunks) || []).map((item) => String(item || '')).join('\n');
  const imageBlocks = Number((contextSegments && contextSegments.imageBlocks) || 0);
  const cjkCount = (text.match(/[\u3400-\u9fff]/g) || []).length;
  const nonCjk = text.replace(/[\u3400-\u9fff]/g, ' ');
  const wordCount = (nonCjk.match(/[A-Za-z0-9_]+/g) || []).length;
  const punctuationCount = (nonCjk.match(/[^\sA-Za-z0-9_]/g) || []).length;
  const textEstimate = cjkCount + wordCount + punctuationCount * 0.33;
  const imageEstimate = imageBlocks * ESTIMATED_TOKENS_PER_IMAGE_BLOCK;
  return Math.round(textEstimate + imageEstimate);
}

function collectContextSegments(session) {
  const pending = normalizeContextSegments(session && session.pending_user_message);
  const aggregate = { textChunks: [], imageBlocks: 0 };

  ((session && session.messages) || []).forEach((msg) => {
    const segments = normalizeContextSegments(msg && msg.content);
    aggregate.textChunks.push(...segments.textChunks);
    aggregate.imageBlocks += segments.imageBlocks;
  });

  // pending_user_message is the next round user input not yet merged into messages.
  aggregate.textChunks.push(...pending.textChunks);
  aggregate.imageBlocks += pending.imageBlocks;
  return aggregate;
}

function detectContextSource(session) {
  const hasMessages = ((session && session.messages) || []).length > 0;
  const hasPending = !!(session && session.pending_user_message);
  if (hasMessages && hasPending) return 'messages+pending';
  if (hasMessages) return 'messages';
  if (hasPending) return 'pending';
  return 'messages(empty)';
}

function updateContextGauge(session) {
  if (!contextGaugeEl || !contextGaugeValueEl || !contextGaugePctEl) return;
  const apiPromptTokens = Number(
    (session && session.api_usage && session.api_usage.current_prompt_tokens)
    || (session && session.runtime && session.runtime.context_prompt_tokens)
    || 0
  );
  const displayTokens = Number.isFinite(apiPromptTokens) && apiPromptTokens > 0
    ? Math.round(apiPromptTokens)
    : estimateContextTokens(collectContextSegments(session));
  const source = Number.isFinite(apiPromptTokens) && apiPromptTokens > 0
    ? 'api_prompt_tokens'
    : detectContextSource(session);
  const runtimeLimit = Number(session && session.runtime && session.runtime.context_limit_tokens);
  const limit = Number.isFinite(runtimeLimit) && runtimeLimit > 0 ? runtimeLimit : DEFAULT_CONTEXT_LIMIT_TOKENS;
  const ratio = limit > 0 ? Math.min(1, displayTokens / limit) : 0;
  const level = ratio >= 0.85 ? 'high' : ratio >= 0.6 ? 'medium' : 'low';
  contextGaugeEl.dataset.level = level;
  contextGaugeEl.style.setProperty('--ratio', String(ratio));
  contextGaugeValueEl.textContent = formatInteger(displayTokens);
  contextGaugePctEl.textContent = `${Math.round(ratio * 100)}%`;
  const hintEl = document.getElementById('contextGaugeHint');
  const cumulativeApiTokens = Number(
    (session && session.api_usage && session.api_usage.cumulative_total_tokens)
    || (session && session.runtime && session.runtime.api_cumulative_tokens)
    || 0
  );
  if (hintEl) hintEl.textContent = `上下文 · ${source} · 累积 ${formatInteger(cumulativeApiTokens)}`;
  contextGaugeEl.title = `当前上下文长度: ${displayTokens} / ${limit} tokens（来源: ${source}）`;
  if (apiTokenCostEl) {
    apiTokenCostEl.textContent = `API累计 tokens: ${formatInteger(cumulativeApiTokens)}`;
  }
}

function formatRuntime(session) {
  const runtime = session.runtime || {};
  const retry = runtime.retry || null;
  const lines = [
    `session_id: ${session.id}`,
    `status: ${session.status}`,
    `model: ${session.selected_model || 'openai'}`,
    `phase: ${runtime.phase || 'idle'}`,
    `workspace: ${session.workspace}`,
    `run_dir: ${session.run_dir}`,
  ];
  if (retry) {
    lines.push(`retry: ${retry.attempt}/${retry.max_attempts} · wait=${retry.wait_seconds ?? retry.next_delay ?? 0}s`);
  }
  if (runtime.last_error) lines.push(`last_error: ${runtime.last_error}`);
  return lines.join('\n');
}

function renderSessions(items) {
  sessionsEl.innerHTML = '';
  items.forEach((session) => {
    const div = document.createElement('div');
    div.className = `session-item ${activeSessionId === session.id ? 'active' : ''}`;
    div.innerHTML = `
      <div class="session-main">
        <div class="session-title">${escapeHtml(session.title)}</div>
        <div class="session-meta">${escapeHtml(summarizeStatus(session.status))} · ${escapeHtml(session.id)}</div>
      </div>
      <div class="session-badges">
        <span class="status-pill status-${escapeHtml(session.status || 'idle')}">${escapeHtml(summarizeStatus(session.status))}</span>
      </div>
    `;
    div.onclick = async () => {
      if (activeSessionId === session.id) return;
      activeSessionId = session.id;
      currentWorkspacePath = '';
      activeFilePath = null;
      lastFlowSignature = '';
      lastMetaSignature = '';
      latestRenderState = { flow: [], finish: null };
      await refreshSessions();
      await refreshSessionDetail({ refreshWorkspaceTree: true, force: true });
      openSessionStream();
      setStatusToast('已切换会话');
    };
    sessionsEl.appendChild(div);
  });
}

function renderMessages(messages) {
  messagesEl.innerHTML = '';
  messages.forEach((msg) => {
    const div = document.createElement('div');
    div.className = `message message-${escapeHtml(msg.role || 'assistant')}`;
    const content = msg.content;
    const body = typeof content === 'string'
      ? content
      : Array.isArray(content)
        ? `[多模态消息] 文本块 ${content.filter((x) => x && x.type === 'text').length} · 图片块 ${content.filter((x) => x && x.type === 'image_url').length}`
        : '';
    div.innerHTML = `
      <div class="message-role">${escapeHtml(msg.role || 'assistant')}</div>
      <div class="message-body">${escapeHtml(body || '')}</div>
    `;
    messagesEl.appendChild(div);
  });
}

function clearSessionPanels() {
  messagesEl.innerHTML = '';
  trajectoryEl.innerHTML = '';
  logsEl.textContent = '请选择或创建一个会话...';
  metaEl.textContent = '未选择会话';
  workspaceTreeEl.innerHTML = '';
  artifactSummaryEl.innerHTML = '<div class="empty-state">暂无产物</div>';
  currentPathEl.textContent = '未选择文件';
  activeFilePath = null;
  currentWorkspacePath = '';
  lastFlowSignature = '';
  lastMetaSignature = '';
  latestRenderState = { flow: [], finish: null };
  setEditorMode('text');
  fileEditorEl.value = '';
  updateContextGauge({ messages: [], events: [], flow: [] });
  if (apiTokenCostEl) apiTokenCostEl.textContent = 'API累计 tokens: 0';
}

function renderArtifacts(artifacts) {
  const recent = (artifacts && artifacts.recent_files) || [];
  if (!recent.length) {
    artifactSummaryEl.innerHTML = '<div class="empty-state">暂无产物</div>';
    return;
  }
  artifactSummaryEl.innerHTML = recent.map((item) => `
    <div class="artifact-item" data-path="${escapeHtml(item.path)}">
      <div class="artifact-main">
        <div class="artifact-path">${escapeHtml(item.path)}</div>
        <div class="artifact-meta">${escapeHtml(String(item.size || 0))} B</div>
      </div>
    </div>
  `).join('');
  artifactSummaryEl.querySelectorAll('.artifact-item').forEach((node) => {
    node.onclick = () => openFile(node.dataset.path);
  });
}

function eventTitle(event) {
  if (event.type === 'llm_request_started') return '模型请求开始';
  if (event.type === 'llm_request_succeeded') return '模型请求成功';
  if (event.type === 'llm_request_failed') return '模型请求失败';
  if (event.type === 'thought') return '思考';
  if (event.type === 'tool_call') return `工具调用 · ${event.tool_name || 'tool'}`;
  if (event.type === 'tool_progress') return `工具进度 · ${event.tool_name || 'tool'}`;
  if (event.type === 'tool_result') return `工具结果 · ${event.tool_name || 'tool'}`;
  if (event.type === 'retry') return '模型重试';
  if (event.type === 'system') return event.label || '系统';
  if (event.type === 'error') return event.label || '错误';
  return event.type;
}

function eventMeta(event) {
  if (event.type === 'llm_request_started') return 'requesting';
  if (event.type === 'llm_request_succeeded') return 'responded';
  if (event.type === 'llm_request_failed') return 'failed';
  if (event.type === 'thought' || event.type === 'tool_call') return `step ${event.step_id || ''}`.trim();
  if (event.type === 'tool_progress') return 'stream';
  if (event.type === 'tool_result') return summarizeStatus(event.status || 'completed');
  if (event.type === 'retry') return `第 ${event.retry_index || '?'} 次 · ${event.wait_seconds || 0}s 后重试`;
  return event.timestamp || '';
}

function eventExtra(event) {
  const body = event.content || '';
  if (!body) return '';
  if (event.type === 'thought') {
    return `<div class="timeline-body thought-body">${escapeHtml(body)}</div>`;
  }
  if (event.type === 'tool_call') {
    return `<details class="inline-details"><summary>参数</summary><pre class="compact-pre">${escapeHtml(body)}</pre></details>`;
  }
  if (event.type === 'tool_result') {
    const open = event.status !== 'completed' && event.status !== 'success' ? 'open' : '';
    return `<details class="inline-details" ${open}><summary>结果</summary><pre class="compact-pre">${escapeHtml(body)}</pre></details>`;
  }
  if (event.type === 'tool_progress' || event.type === 'retry') {
    return `<pre class="compact-pre progress-pre">${escapeHtml(body)}</pre>`;
  }
  return `<div class="timeline-body">${escapeHtml(body)}</div>`;
}

function buildVisibleTimeline(flow) {
  const visible = [];
  let llmSummary = null;

  for (const event of flow || []) {
    if (event.type === 'llm_request_started') {
      llmSummary = {
        type: 'llm_summary',
        label: '模型状态',
        state: 'requesting',
        content: event.content || '',
        successCount: llmSummary ? llmSummary.successCount : 0,
        retryCount: llmSummary ? llmSummary.retryCount : 0,
      };
      continue;
    }

    if (event.type === 'llm_request_succeeded') {
      if (!llmSummary) {
        llmSummary = { type: 'llm_summary', label: '模型状态', state: 'responded', content: '', successCount: 0, retryCount: 0 };
      }
      llmSummary.state = 'responded';
      llmSummary.content = event.content || llmSummary.content;
      llmSummary.successCount = (llmSummary.successCount || 0) + 1;
      continue;
    }

    if (event.type === 'retry') {
      if (!llmSummary) {
        llmSummary = { type: 'llm_summary', label: '模型状态', state: 'retrying', content: '', successCount: 0, retryCount: 0 };
      }
      llmSummary.state = 'retrying';
      llmSummary.content = event.content || llmSummary.content;
      llmSummary.retryCount = (llmSummary.retryCount || 0) + 1;
      visible.push(event);
      continue;
    }

    if (event.type === 'llm_request_failed') {
      if (!llmSummary) {
        llmSummary = { type: 'llm_summary', label: '模型状态', state: 'failed', content: '', successCount: 0, retryCount: 0 };
      }
      llmSummary.state = 'failed';
      llmSummary.content = event.content || llmSummary.content;
      visible.push(event);
      continue;
    }

    visible.push(event);
  }

  if (llmSummary) visible.unshift(llmSummary);
  return visible;
}

function renderWaitingSkeleton(runtime, flowLen) {
  if (flowLen > 0) return;
  const phase = (runtime && runtime.phase) || 'requesting_llm';
  trajectoryEl.innerHTML = `
    <div class="timeline-item timeline-item-waiting">
      <div class="timeline-marker marker-pulse"></div>
      <div class="timeline-card waiting-card">
        <div class="timeline-head">
          <div class="timeline-title">正在获取模型响应</div>
          <div class="timeline-meta">${escapeHtml(phase)}</div>
        </div>
        <div class="skeleton-line"></div>
        <div class="skeleton-line short"></div>
      </div>
    </div>
  `;
}

function renderTimeline(flow, finish, runtime, force = false) {
  const nextSignature = `${(flow || []).length}:${finish ? (finish.status || 'done') : 'none'}:${runtime && runtime.phase ? runtime.phase : ''}`;
  if (!force && nextSignature === lastFlowSignature) return;
  lastFlowSignature = nextSignature;
  latestRenderState = { flow, finish };

  if (!flow.length) {
    renderWaitingSkeleton(runtime, 0);
    return;
  }

  trajectoryEl.innerHTML = '';
  const visibleFlow = buildVisibleTimeline(flow);
  const renderErrors = [];
  visibleFlow.forEach((event, index) => {
    try {
      const item = document.createElement('div');
      item.className = `timeline-item timeline-item-${event.type || 'unknown'}`;
      if (event.type === 'llm_summary') {
        const chips = [];
        chips.push(`<span class="mini-chip">${escapeHtml(summarizeStatus(event.state))}</span>`);
        if (event.successCount) chips.push(`<span class="mini-chip">${escapeHtml(String(event.successCount))} 次响应</span>`);
        if (event.retryCount) chips.push(`<span class="mini-chip">${escapeHtml(String(event.retryCount))} 次重试</span>`);
        item.innerHTML = `
          <div class="timeline-marker"></div>
          <div class="timeline-card llm-summary-card">
            <div class="timeline-head">
              <div class="timeline-title">模型状态</div>
              <div class="timeline-chips">${chips.join('')}</div>
            </div>
            ${event.content ? `<div class="timeline-body">${escapeHtml(String(event.content))}</div>` : ''}
          </div>
        `;
        trajectoryEl.appendChild(item);
        return;
      }
      item.innerHTML = `
        <div class="timeline-marker"></div>
        <div class="timeline-card">
          <div class="timeline-head">
            <div class="timeline-title">${escapeHtml(eventTitle(event || {}))}</div>
            <div class="timeline-meta">${escapeHtml(eventMeta(event || {}))}</div>
          </div>
          ${eventExtra(event || {})}
        </div>
      `;
      trajectoryEl.appendChild(item);
    } catch (err) {
      console.error('timeline render event failed', index, event, err);
      renderErrors.push(index);
    }
  });

  if (renderErrors.length) {
    const warn = document.createElement('div');
    warn.className = 'timeline-item timeline-item-error';
    warn.innerHTML = `
      <div class="timeline-marker"></div>
      <div class="timeline-card">
        <div class="timeline-head">
          <div class="timeline-title">轨迹渲染告警</div>
          <div class="timeline-meta">${renderErrors.length} 条事件渲染失败</div>
        </div>
      </div>
    `;
    trajectoryEl.appendChild(warn);
  }

  if (finish) {
    const card = document.createElement('div');
    card.className = `timeline-item timeline-item-finish finish-${finish.status || 'completed'}`;
    const titleMap = { completed: '已完成', failed: '已失败', cancelled: '已取消' };
    card.innerHTML = `
      <div class="timeline-marker"></div>
      <div class="timeline-card">
        <div class="timeline-head">
          <div class="timeline-title">${escapeHtml(titleMap[finish.status] || '已结束')}</div>
          <div class="timeline-chips">
            <span class="mini-chip">${escapeHtml(summarizeStatus(finish.status))}</span>
            <span class="mini-chip">${escapeHtml(String(finish.step_count || 0))} step</span>
            <span class="mini-chip">${escapeHtml(String(finish.tool_count || 0))} tool</span>
          </div>
        </div>
        ${finish.summary ? `<div class="timeline-body">${escapeHtml(finish.summary)}</div>` : ''}
      </div>
    `;
    trajectoryEl.appendChild(card);
  }
}

async function refreshSessions() {
  try {
    const data = await requestJson('/api/sessions');
    renderSessions(data.sessions || []);
  } catch (err) {
    debugLog('refreshSessions failed', err);
    setStatusToast(`刷新会话失败: ${err.message || err}`, 'warn');
  }
}

async function refreshSessionDetail(options = {}) {
  if (!activeSessionId) return;
  const { refreshWorkspaceTree = false, force = false } = options;
  let session = null;
  try {
    session = await requestJson(`/api/session?id=${encodeURIComponent(activeSessionId)}`);
  } catch (err) {
    debugLog('refreshSessionDetail failed', err);
    setStatusToast(`读取会话失败: ${err.message || err}`, 'warn');
    return;
  }

  if (modelSelectEl && session.selected_model) modelSelectEl.value = session.selected_model;

  const metaText = formatRuntime(session);
  if (force || metaText !== lastMetaSignature) {
    metaEl.textContent = metaText;
    lastMetaSignature = metaText;
  }
  updateContextGauge(session);

  renderMessages(session.messages || []);
  renderArtifacts(session.artifacts || null);
  renderTimeline(session.flow || [], session.finish || null, session.runtime || {}, force);
  logsEl.textContent = session.logs || '';

  if (refreshWorkspaceTree) await refreshWorkspace(currentWorkspacePath);
}

function closeSessionStream() {
  if (sessionStream) {
    sessionStream.close();
    sessionStream = null;
  }
  streamSessionId = null;
  if (sessionRefreshTimer) {
    clearTimeout(sessionRefreshTimer);
    sessionRefreshTimer = null;
  }
}

function openSessionStream() {
  if (!activeSessionId) return;
  if (sessionStream && streamSessionId === activeSessionId) return;
  closeSessionStream();
  streamSessionId = activeSessionId;
  sessionStream = new EventSource(`/api/session/stream?id=${encodeURIComponent(activeSessionId)}`);
  sessionStream.addEventListener('session', async () => {
    if (sessionRefreshTimer) clearTimeout(sessionRefreshTimer);
    sessionRefreshTimer = setTimeout(async () => {
      if (streamSessionId !== activeSessionId) return;
      await refreshSessionDetail({ refreshWorkspaceTree: true });
    }, 120);
  });
  sessionStream.onerror = () => {
    if (streamSessionId !== activeSessionId) return;
    closeSessionStream();
    sessionRefreshTimer = setTimeout(() => {
      if (activeSessionId) openSessionStream();
    }, 1200);
  };
}

async function refreshWorkspace(path = currentWorkspacePath) {
  if (!activeSessionId) return;
  currentWorkspacePath = path || '';
  let data = null;
  try {
    data = await requestJson(`/api/workspace/list?session_id=${encodeURIComponent(activeSessionId)}&path=${encodeURIComponent(currentWorkspacePath)}`);
  } catch (err) {
    debugLog('refreshWorkspace failed', err);
    setStatusToast(`刷新文件树失败: ${err.message || err}`, 'warn');
    return;
  }
  workspaceTreeEl.innerHTML = '';

  if (currentWorkspacePath) {
    const up = document.createElement('div');
    up.className = 'tree-item';
    up.textContent = '⬆ 返回上级';
    up.onclick = () => {
      const parent = currentWorkspacePath.split('/').slice(0, -1).join('/');
      refreshWorkspace(parent);
    };
    workspaceTreeEl.appendChild(up);
  }

  (data.items || []).forEach((item) => {
    const div = document.createElement('div');
    div.className = 'tree-item';
    div.innerHTML = `<span>${item.is_dir ? '📁' : '📄'}</span><span>${escapeHtml(item.name)}</span>`;
    div.onclick = () => item.is_dir ? refreshWorkspace(item.path) : openFile(item.path);
    workspaceTreeEl.appendChild(div);
  });
}

async function openFile(path) {
  if (!activeSessionId) return;
  activeFilePath = path;
  currentPathEl.textContent = path;
  if (isPreviewImage(path)) {
    setEditorMode('image', path);
    return;
  }
  let data = null;
  try {
    data = await requestJson(`/api/workspace/read?session_id=${encodeURIComponent(activeSessionId)}&path=${encodeURIComponent(path)}`);
  } catch (err) {
    debugLog('openFile failed', err);
    setStatusToast(`打开文件失败: ${err.message || err}`, 'warn');
    return;
  }
  setEditorMode('text', path);
  fileEditorEl.value = data.content || '';
}

async function saveFile() {
  if (!activeSessionId || !activeFilePath) {
    setStatusToast('请先选择文件', 'warn');
    return;
  }
  const saveBtn = document.getElementById('saveFileBtn');
  setBusy(saveBtn, true, '保存中...');
  try {
    await requestJson('/api/workspace/write', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: activeSessionId, path: activeFilePath, content: fileEditorEl.value })
    });
    await refreshSessionDetail({ refreshWorkspaceTree: true, force: true });
    setStatusToast('文件已保存', 'success');
  } catch (err) {
    debugLog('saveFile failed', err);
    setStatusToast(`保存失败: ${err.message || err}`, 'warn');
  } finally {
    setBusy(saveBtn, false);
  }
}

async function createSession() {
  try {
    const messagePayload = buildOutgoingMessagePayload(inputEl.value);
    const hasMessage = Array.isArray(messagePayload) ? messagePayload.length > 0 : Boolean(String(messagePayload || '').trim());
    const data = await requestJson('/api/session/create', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: hasMessage ? messagePayload : '', model: modelSelectEl ? modelSelectEl.value : 'openai' })
    });
    activeSessionId = data.session_id;
    inputEl.value = '';
    clearPendingMessageImages();
    currentWorkspacePath = '';
    activeFilePath = null;
    lastFlowSignature = '';
    lastMetaSignature = '';
    latestRenderState = { flow: [], finish: null };
    if (stagedUploads.length) {
      await flushStagedUploads();
    }
    await refreshSessions();
    await refreshSessionDetail({ refreshWorkspaceTree: true, force: true });
    openSessionStream();
    setStatusToast('会话已创建', 'success');
  } catch (err) {
    debugLog('createSession failed', err);
    setStatusToast(`创建会话失败: ${err.message || err}`, 'warn');
  }
}

async function clearActiveSession() {
  if (!activeSessionId) {
    setStatusToast('请先选择会话', 'warn');
    return;
  }
  const ok = window.confirm(`确认清除会话 ${activeSessionId} 及其工作区吗？此操作不可恢复。`);
  if (!ok) return;

  const clearBtn = document.getElementById('clearSessionBtn');
  setBusy(clearBtn, true, '清除中...');
  try {
    const sessionId = activeSessionId;
    await requestJson('/api/session/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, remove_workspace: true })
    });
    closeSessionStream();
    activeSessionId = null;
    clearSessionPanels();
    await refreshSessions();
    setStatusToast(`会话 ${sessionId} 已清除`, 'success');
  } catch (err) {
    debugLog('clearActiveSession failed', err);
    if (err && err.message === 'session_running') {
      setStatusToast('会话正在运行，无法清除', 'warn');
    } else if (err && err.message === 'not_found') {
      setStatusToast('后端未加载删除接口，请重启 web 服务', 'warn');
    } else {
      setStatusToast(`清除失败: ${err.message || err}`, 'warn');
    }
  } finally {
    setBusy(clearBtn, false);
  }
}

async function runSession() {
  const runBtn = document.getElementById('runBtn');
  setBusy(runBtn, true, '运行中...');
  try {
  const messagePayload = buildOutgoingMessagePayload(inputEl.value);
  const hasMessage = Array.isArray(messagePayload) ? messagePayload.length > 0 : Boolean(String(messagePayload || '').trim());
  let createdNow = false;
  if (!activeSessionId) {
    if (!hasMessage) {
      setStatusToast('将创建空会话并导入缓存文件', 'info');
    }
    const data = await requestJson('/api/session/create', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: hasMessage ? messagePayload : '', model: modelSelectEl ? modelSelectEl.value : 'openai' })
    });
    activeSessionId = data.session_id;
    inputEl.value = '';
    clearPendingMessageImages();
    currentWorkspacePath = '';
    activeFilePath = null;
    lastFlowSignature = '';
    lastMetaSignature = '';
    latestRenderState = { flow: [], finish: null };
    createdNow = true;
    if (stagedUploads.length) {
      await flushStagedUploads();
    }
    await refreshSessions();
  }
  if (activeSessionId && stagedUploads.length) {
    await flushStagedUploads();
  }
  if (activeSessionId && hasMessage && !createdNow) {
    await requestJson('/api/session/message', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: activeSessionId, message: messagePayload })
    });
    inputEl.value = '';
    clearPendingMessageImages();
  }
  if (createdNow && !hasMessage) {
    await refreshSessionDetail({ refreshWorkspaceTree: true, force: true });
    openSessionStream();
    setStatusToast('会话已创建，可先继续上传或输入消息后再运行', 'success');
    return;
  }
  await requestJson('/api/session/run', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: activeSessionId })
  });
  await refreshSessionDetail({ refreshWorkspaceTree: true, force: true });
  openSessionStream();
  await refreshSessions();
  setStatusToast('开始运行', 'success');
  } catch (err) {
    debugLog('runSession failed', err);
    setStatusToast(`运行失败: ${err.message || err}`, 'warn');
  } finally {
    setBusy(runBtn, false, '运行');
  }
}

async function terminateSession() {
  if (!activeSessionId) {
    setStatusToast('请先选择会话', 'warn');
    return;
  }
  const terminateBtn = document.getElementById('terminateBtn');
  setBusy(terminateBtn, true, '终止中...');
  try {
    await requestJson('/api/session/terminate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: activeSessionId })
    });
    await refreshSessionDetail({ refreshWorkspaceTree: true, force: true });
    await refreshSessions();
    setStatusToast('已发送终止请求', 'success');
  } catch (err) {
    debugLog('terminateSession failed', err);
    if (err && err.message === 'session_not_running') {
      setStatusToast('会话当前不在运行状态', 'warn');
    } else {
      setStatusToast(`终止失败: ${err.message || err}`, 'warn');
    }
  } finally {
    setBusy(terminateBtn, false);
  }
}

async function updateSessionModel() {
  if (!activeSessionId || !modelSelectEl) return;
  try {
    await requestJson('/api/session/model', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: activeSessionId, model: modelSelectEl.value })
    });
    await refreshSessionDetail({ force: true });
    setStatusToast('模型已切换');
  } catch (err) {
    debugLog('updateSessionModel failed', err);
    setStatusToast(`模型切换失败: ${err.message || err}`, 'warn');
  }
}

async function newDir() {
  if (!activeSessionId) {
    setStatusToast('请先选择会话', 'warn');
    return;
  }
  const path = prompt('请输入新目录路径（相对 workspace）');
  if (!path) return;
  try {
    await requestJson('/api/workspace/mkdir', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: activeSessionId, path })
    });
    await refreshSessionDetail({ refreshWorkspaceTree: true, force: true });
    setStatusToast('目录已创建', 'success');
  } catch (err) {
    debugLog('newDir failed', err);
    setStatusToast(`新建目录失败: ${err.message || err}`, 'warn');
  }
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || '');
      const idx = result.indexOf(',');
      resolve(idx >= 0 ? result.slice(idx + 1) : result);
    };
    reader.onerror = () => reject(reader.error || new Error('file_read_failed'));
    reader.readAsDataURL(file);
  });
}

async function uploadFile() {
  const input = document.createElement('input');
  input.type = 'file';
  input.multiple = false;
  input.onchange = async () => {
    const file = input.files && input.files[0];
    if (!file) return;
    const uploadBtn = document.getElementById('uploadFileBtn');
    setBusy(uploadBtn, true, '上传中...');
    try {
      const contentBase64 = await fileToBase64(file);
      if (!activeSessionId) {
        stagedUploads.push({
          filename: file.name,
          path: '',
          content_base64: contentBase64
        });
        updateUploadButtonLabel();
        setStatusToast(`已缓存: ${file.name}，创建会话后自动加入`, 'success');
        return;
      }
      await requestJson('/api/workspace/upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: activeSessionId,
          path: currentWorkspacePath || '',
          filename: file.name,
          content_base64: contentBase64
        })
      });
      await refreshSessionDetail({ refreshWorkspaceTree: true, force: true });
      setStatusToast(`上传成功: ${file.name}`, 'success');
    } catch (err) {
      debugLog('uploadFile failed', err);
      setStatusToast(`上传失败: ${err.message || err}`, 'warn');
    } finally {
      setBusy(uploadBtn, false);
    }
  };
  input.click();
}

async function addMessageImageFiles(files, sourceLabel = '附加') {
  const validFiles = (files || []).filter((f) => f && String(f.type || '').startsWith('image/'));
  if (!validFiles.length) return;
  const attachBtn = document.getElementById('attachImageBtn');
  setBusy(attachBtn, true, '处理中...');
  let added = 0;
  try {
    for (const file of validFiles) {
      const b64 = await fileToBase64(file);
      const mime = file.type || 'image/png';
      const fallbackName = `clipboard-${Date.now()}.png`;
      const ok = appendPendingMessageImage(file.name || fallbackName, `data:${mime};base64,${b64}`);
      if (ok) added += 1;
    }
    renderMessageAttachments();
    setStatusToast(`${sourceLabel}图片 ${added} 张`, 'success');
  } catch (err) {
    debugLog('addMessageImageFiles failed', err);
    setStatusToast(`附加失败: ${err.message || err}`, 'warn');
  } finally {
    setBusy(attachBtn, false);
  }
}

async function addStagedUploadFiles(files, sourceLabel = '已缓存') {
  const validFiles = (files || []).filter((f) => f && (String(f.type || '').startsWith('image/') || String(f.type || '') === 'application/pdf'));
  if (!validFiles.length) return;
  const uploadBtn = document.getElementById('uploadFileBtn');
  setBusy(uploadBtn, true, '缓存中...');
  try {
    for (const file of validFiles) {
      const contentBase64 = await fileToBase64(file);
      stagedUploads.push({
        filename: file.name || `clipboard-${Date.now()}`,
        path: '',
        content_base64: contentBase64
      });
    }
    updateUploadButtonLabel();
    setStatusToast(`${sourceLabel}文件 ${validFiles.length} 个`, 'success');
  } catch (err) {
    debugLog('addStagedUploadFiles failed', err);
    setStatusToast(`缓存失败: ${err.message || err}`, 'warn');
  } finally {
    setBusy(uploadBtn, false);
  }
}

function attachMessageImage() {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = 'image/png,image/jpeg,image/jpg,image/webp,image/gif';
  input.multiple = true;
  input.onchange = async () => {
    const files = Array.from(input.files || []);
    if (!files.length) return;
    await addMessageImageFiles(files, '已附加');
  };
  input.click();
}

function getClipboardImageFiles(event) {
  const items = Array.from((event.clipboardData && event.clipboardData.items) || []);
  const directFiles = Array.from((event.clipboardData && event.clipboardData.files) || [])
    .filter((file) => file && String(file.type || '').startsWith('image/'));
  const files = [];
  const seen = new Set();
  const pushUniqueFile = (file) => {
    if (!file) return;
    const key = [
      String(file.name || ''),
      String(file.type || ''),
      String(file.size || 0),
      String(file.lastModified || 0),
    ].join('|');
    if (seen.has(key)) return;
    seen.add(key);
    files.push(file);
  };
  if (directFiles.length) directFiles.forEach(pushUniqueFile);
  for (const item of items) {
    if (!item || !String(item.type || '').startsWith('image/')) continue;
    const file = item.getAsFile();
    if (file) pushUniqueFile(file);
  }
  return files;
}

function getClipboardImageUrls(event) {
  const html = String((event.clipboardData && event.clipboardData.getData('text/html')) || '').trim();
  if (!html) return [];
  const urls = [];
  const imgTagRegex = /<img\b[^>]*\bsrc=["']([^"']+)["'][^>]*>/gi;
  let match = imgTagRegex.exec(html);
  while (match) {
    const src = String(match[1] || '').trim();
    if (src.startsWith('data:image/') || src.startsWith('http://') || src.startsWith('https://')) {
      urls.push(src);
    }
    match = imgTagRegex.exec(html);
  }
  return urls;
}

function getClipboardPdfFiles(event) {
  const items = Array.from((event.clipboardData && event.clipboardData.items) || []);
  const files = [];
  for (const item of items) {
    if (!item || String(item.type || '') !== 'application/pdf') continue;
    const file = item.getAsFile();
    if (file) files.push(file);
  }
  return files;
}

function makePasteSignature(event) {
  const items = Array.from((event.clipboardData && event.clipboardData.items) || [])
    .map((item) => `${item.kind || ''}:${item.type || ''}`)
    .sort()
    .join('|');
  const files = Array.from((event.clipboardData && event.clipboardData.files) || [])
    .map((file) => `${file.name || ''}:${file.type || ''}:${file.size || 0}`)
    .sort()
    .join('|');
  return `${items}@@${files}`;
}

async function handlePasteMessageImages(event) {
  if (event.defaultPrevented) return;
  const pasteSignature = makePasteSignature(event);
  const now = Date.now();
  if (pasteSignature && pasteSignature === lastPasteSignature && now - lastPasteHandledAt < 800) {
    event.preventDefault();
    return;
  }
  const imageFiles = getClipboardImageFiles(event);
  const imageUrls = imageFiles.length ? [] : getClipboardImageUrls(event);
  const pdfFiles = getClipboardPdfFiles(event);
  if (!imageFiles.length && !imageUrls.length && !pdfFiles.length) return;
  lastPasteSignature = pasteSignature;
  lastPasteHandledAt = now;
  event.preventDefault();
  if (imageFiles.length) {
    await addMessageImageFiles(imageFiles, '已粘贴');
  }
  if (imageUrls.length) {
    const cleaned = imageUrls.filter((url) => url.trim());
    let added = 0;
    cleaned.forEach((url, index) => {
      if (appendPendingMessageImage(`clipboard-url-${Date.now()}-${index + 1}`, url.trim())) {
        added += 1;
      }
    });
    renderMessageAttachments();
    setStatusToast(`已粘贴图片 ${added} 张`, 'success');
  }
  if (pdfFiles.length) {
    await addStagedUploadFiles(pdfFiles, '已粘贴并缓存');
  }
}

async function flushStagedUploads() {
  if (!activeSessionId || !stagedUploads.length) return;
  const queue = [...stagedUploads];
  let uploaded = 0;
  for (const item of queue) {
    await requestJson('/api/workspace/upload', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: activeSessionId,
        path: item.path || '',
        filename: item.filename,
        content_base64: item.content_base64
      })
    });
    uploaded += 1;
  }
  stagedUploads.splice(0, uploaded);
  updateUploadButtonLabel();
  setStatusToast(`已加入缓存文件 ${uploaded} 个`, 'success');
}

function bindTabs() {
  tabButtons.forEach((btn) => {
    btn.onclick = () => {
      const target = btn.dataset.tab;
      activeTab = target;
      tabButtons.forEach((item) => item.classList.toggle('active', item === btn));
      tabContents.forEach((panel) => panel.classList.toggle('active', panel.id === `tab-${target}`));
    };
  });
}

document.getElementById('newSessionTopBtn').onclick = createSession;
document.getElementById('clearSessionBtn').onclick = clearActiveSession;
document.getElementById('uploadFileBtn').onclick = uploadFile;
document.getElementById('attachImageBtn').onclick = attachMessageImage;
document.getElementById('refreshWorkspace').onclick = () => refreshWorkspace(currentWorkspacePath);
document.getElementById('runBtn').onclick = runSession;
document.getElementById('terminateBtn').onclick = terminateSession;
document.getElementById('saveFileBtn').onclick = saveFile;
document.getElementById('newDirBtn').onclick = newDir;
if (modelSelectEl) modelSelectEl.onchange = updateSessionModel;
if (inputEl) inputEl.addEventListener('paste', (event) => {
  event.stopPropagation();
  handlePasteMessageImages(event);
});
window.addEventListener('paste', (event) => {
  if (event.target === inputEl || document.activeElement === inputEl) return;
  handlePasteMessageImages(event);
});
window.addEventListener('beforeunload', () => closeSessionStream());

bindTabs();
updateUploadButtonLabel();
renderMessageAttachments();
refreshSessions();
