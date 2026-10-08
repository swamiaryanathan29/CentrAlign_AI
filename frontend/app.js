/* ═══════════════════════════════════════════════════════
   CentrAlign AI Worker — Frontend Application
   Real-time agent activity streaming via SSE
═══════════════════════════════════════════════════════ */

const API = '';  // same-origin

let activeTaskId = null;
let activeEventSource = null;
let allTasks = [];

/* ─────────────────── Init ─────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  checkHealth();
  loadTaskHistory();
  setupEventListeners();
});

function setupEventListeners() {
  // Run button
  document.getElementById('run-btn').addEventListener('click', submitTask);

  // Ctrl+Enter to submit
  document.getElementById('task-input').addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') submitTask();
  });

  // Quick task buttons
  document.querySelectorAll('.qt-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.getElementById('task-input').value = btn.dataset.task;
      document.getElementById('task-input').focus();
    });
  });

  // Close modal on overlay click
  document.getElementById('erp-modal').addEventListener('click', e => {
    if (e.target === document.getElementById('erp-modal')) closeErpModal();
  });
}

/* ─────────────────── Health Check ─────────────────── */
async function checkHealth() {
  try {
    const res = await fetch(`${API}/api/health`);
    if (res.ok) {
      setStatus('online', 'System Ready');
    } else {
      setStatus('error', 'API Error');
    }
  } catch {
    setStatus('error', 'Disconnected');
  }
}

function setStatus(state, text) {
  const dot = document.getElementById('system-dot');
  const label = document.getElementById('system-status');
  dot.className = 'status-dot ' + state;
  label.textContent = text;
}

/* ─────────────────── Submit Task ──────────────────── */
async function submitTask() {
  const input = document.getElementById('task-input');
  const task = input.value.trim();
  if (!task) { input.focus(); return; }

  const btn = document.getElementById('run-btn');
  btn.disabled = true;
  btn.innerHTML = `<div class="thinking-dots"><span></span><span></span><span></span></div> Starting…`;

  clearFeed();
  hideSummary();

  try {
    const res = await fetch(`${API}/api/tasks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to start task');
    }

    const data = await res.json();
    activeTaskId = data.task_id;

    // Show badge
    const badge = document.getElementById('active-task-badge');
    badge.className = 'badge live';
    badge.textContent = '● Live';
    badge.style.display = '';

    addFeedItem('status', '🧠', 'Task Received', `ID: ${data.task_id} — Agent is analyzing your request…`, null);
    addProgressBar();

    // Stream events
    startSSEStream(data.task_id);

    // Refresh task list
    setTimeout(loadTaskHistory, 500);

  } catch (e) {
    addFeedItem('error', '❌', 'Error', e.message, null);
    setRunBtnReady();
  }
}

/* ─────────────────── SSE Stream ───────────────────── */
function startSSEStream(taskId) {
  if (activeEventSource) activeEventSource.close();

  activeEventSource = new EventSource(`${API}/api/tasks/${taskId}/stream`);

  activeEventSource.onmessage = (e) => {
    const event = JSON.parse(e.data);
    handleEvent(event, taskId);
  };

  activeEventSource.onerror = () => {
    activeEventSource.close();
    // Fetch final state
    fetchTaskFinal(taskId);
  };
}

function handleEvent(event, taskId) {
  switch (event.type) {
    case 'heartbeat':
      break;

    case 'status':
      break;

    case 'step': {
      const step = event.step;
      if (step.type === 'tool_call') {
        addFeedItem(
          'tool',
          '🔧',
          `Tool Call: ${formatToolName(step.action)}`,
          formatArgs(step.args),
          step.timestamp,
          step.result ? `Result: ${step.result}` : null,
        );
      } else if (step.type === 'final_answer') {
        // Don't add here — we'll show in the done event
      }
      break;
    }

    case 'done': {
      activeEventSource?.close();
      removeProgressBar();
      hideLiveBadge();
      setRunBtnReady();

      if (event.status === 'completed') {
        addFeedItem('done', '✅', 'Task Complete', 'Agent finished all steps successfully.', null);
        if (event.final_summary) {
          showSummary(event.final_summary);
        }
      } else {
        addFeedItem('error', '❌', 'Task Failed', event.error || 'Unknown error', null);
        showErrorSummary(event.error);
      }

      loadTaskHistory();
      break;
    }
  }
}

async function fetchTaskFinal(taskId) {
  try {
    const res = await fetch(`${API}/api/tasks/${taskId}`);
    const data = await res.json();
    handleEvent({ type: 'done', status: data.status, final_summary: data.final_summary, error: data.error }, taskId);
  } catch {
    setRunBtnReady();
    hideLiveBadge();
  }
}

/* ─────────────────── Feed Helpers ─────────────────── */
function clearFeed() {
  document.getElementById('activity-feed').innerHTML = '';
}

function addFeedItem(type, icon, title, subtext, timestamp, codeblock) {
  const feed = document.getElementById('activity-feed');

  // Remove placeholder
  const placeholder = feed.querySelector('.feed-placeholder');
  if (placeholder) placeholder.remove();

  const iconClass = {
    status:  'icon-think',
    tool:    'icon-tool',
    observe: 'icon-observe',
    error:   'icon-error',
    done:    'icon-done',
  }[type] || 'icon-think';

  const el = document.createElement('div');
  el.className = 'feed-item';
  el.innerHTML = `
    <div class="feed-icon ${iconClass}">${icon}</div>
    <div class="feed-content">
      <div class="feed-title">${escHtml(title)}</div>
      ${subtext ? `<div class="feed-sub">${escHtml(subtext)}</div>` : ''}
      ${codeblock ? `<div class="feed-code">${escHtml(codeblock)}</div>` : ''}
      ${timestamp ? `<div class="feed-time">${formatTime(timestamp)}</div>` : ''}
    </div>
  `;
  feed.appendChild(el);
  feed.scrollTop = feed.scrollHeight;
}

function addProgressBar() {
  const feed = document.getElementById('activity-feed');
  const bar = document.createElement('div');
  bar.id = 'progress-wrap';
  bar.className = 'progress-bar-wrap';
  bar.innerHTML = '<div class="progress-bar indeterminate"></div>';
  feed.appendChild(bar);
}

function removeProgressBar() {
  document.getElementById('progress-wrap')?.remove();
}

function showSummary(text) {
  const panel = document.getElementById('summary-panel');
  const body = document.getElementById('summary-body');
  body.textContent = text;
  panel.style.display = '';
  panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function showErrorSummary(text) {
  const panel = document.getElementById('summary-panel');
  const body = document.getElementById('summary-body');
  panel.style.background = 'rgba(239,68,68,0.05)';
  panel.querySelector('.summary-icon').textContent = '❌';
  panel.querySelector('h3').textContent = 'Task Failed';
  panel.querySelector('h3').style.color = 'var(--red)';
  body.textContent = text || 'The agent encountered an error.';
  panel.style.display = '';
}

function hideSummary() {
  const panel = document.getElementById('summary-panel');
  panel.style.display = 'none';
  panel.style.background = '';
  const icon = panel.querySelector('.summary-icon');
  const h3 = panel.querySelector('h3');
  if (icon) icon.textContent = '✅';
  if (h3) { h3.textContent = 'Task Complete'; h3.style.color = ''; }
}

function hideLiveBadge() {
  const badge = document.getElementById('active-task-badge');
  badge.style.display = 'none';
}

function setRunBtnReady() {
  const btn = document.getElementById('run-btn');
  btn.disabled = false;
  btn.innerHTML = '<span class="run-icon">▶</span> Run Agent';
}

/* ─────────────────── Task History ─────────────────── */
async function loadTaskHistory() {
  try {
    const res = await fetch(`${API}/api/tasks`);
    const data = await res.json();
    allTasks = data.tasks;
    renderTaskList(allTasks);
    document.getElementById('task-count').textContent = `${allTasks.length} task${allTasks.length !== 1 ? 's' : ''}`;
  } catch {
    // ignore
  }
}

function renderTaskList(tasks) {
  const list = document.getElementById('task-list');
  if (!tasks.length) {
    list.innerHTML = '<div class="empty-state">No tasks yet. Submit one above ↑</div>';
    return;
  }
  list.innerHTML = tasks.map(t => `
    <div class="task-card ${t.task_id === activeTaskId ? 'active' : ''}" onclick="selectTask('${t.task_id}')">
      <div class="task-card-header">
        <span class="task-id">#${t.task_id}</span>
        <span class="task-status-pill pill-${t.status}">${t.status}</span>
      </div>
      <div class="task-card-text">${escHtml(t.original_task)}</div>
      <div class="task-card-meta">
        ${t.steps} step${t.steps !== 1 ? 's' : ''} · ${relativeTime(t.created_at)}
      </div>
    </div>
  `).join('');
}

async function selectTask(taskId) {
  activeTaskId = taskId;
  renderTaskList(allTasks);
  clearFeed();
  hideSummary();

  try {
    const res = await fetch(`${API}/api/tasks/${taskId}`);
    const task = await res.json();

    addFeedItem('status', '📋', `Task #${task.task_id}`, task.original_task, task.created_at);

    for (const step of task.step_log) {
      if (step.type === 'tool_call') {
        addFeedItem(
          'tool', '🔧',
          `Tool: ${formatToolName(step.action)}`,
          formatArgs(step.args),
          step.timestamp,
          step.result,
        );
      } else if (step.type === 'final_answer') {
        addFeedItem('done', '✅', 'Final Answer', step.content, step.timestamp);
      }
    }

    if (task.status === 'completed' && task.final_summary) {
      showSummary(task.final_summary);
    } else if (task.status === 'failed') {
      showErrorSummary(task.error);
    } else if (task.status === 'running') {
      startSSEStream(taskId);
    }
  } catch (e) {
    addFeedItem('error', '❌', 'Error loading task', e.message, null);
  }
}

/* ─────────────────── ERP Modal ─────────────────────── */
async function openErpModal() {
  document.getElementById('erp-modal').style.display = 'flex';
  const body = document.getElementById('erp-body');
  body.innerHTML = '<div style="color:var(--text3);text-align:center;padding:20px">Loading ERP records…</div>';

  try {
    const res = await fetch('http://localhost:8001/payables');
    const data = await res.json();

    if (!data.payables.length) {
      body.innerHTML = '<div style="color:var(--text3);text-align:center;padding:20px">No payable records yet. Run an invoice task to populate the ERP.</div>';
      return;
    }

    body.innerHTML = data.payables.map(p => `
      <div class="erp-record">
        <div class="erp-record-header">
          <span class="erp-id">${p.record_id}</span>
          <span class="task-status-pill pill-${mapErpStatus(p.status)}">${p.status}</span>
        </div>
        <div class="erp-grid">
          <div class="erp-field"><label>Invoice ID</label><value>${p.invoice_id}</value></div>
          <div class="erp-field"><label>Vendor</label><value>${p.vendor}</value></div>
          <div class="erp-field"><label>Company</label><value>${p.company}</value></div>
          <div class="erp-field"><label>Due Date</label><value>${p.due_date}</value></div>
          <div class="erp-field"><label>Amount</label><value class="erp-amount">${p.currency} ${Number(p.amount).toLocaleString('en-US', {minimumFractionDigits: 2})}</value></div>
          <div class="erp-field"><label>Created</label><value>${formatTime(p.created_at)}</value></div>
        </div>
        ${p.notes ? `<div style="margin-top:8px;font-size:0.75rem;color:var(--text3)">📝 ${p.notes}</div>` : ''}
      </div>
    `).join('');
  } catch {
    body.innerHTML = '<div style="color:var(--red);text-align:center;padding:20px">Could not connect to ERP system. Make sure it\'s running on port 8001.</div>';
  }
}

function closeErpModal() {
  document.getElementById('erp-modal').style.display = 'none';
}

function mapErpStatus(s) {
  if (s === 'approved' || s === 'paid') return 'completed';
  if (s === 'rejected') return 'failed';
  if (s === 'pending_approval') return 'running';
  return 'pending';
}

/* ─────────────────── Formatting Helpers ───────────── */
function formatToolName(name) {
  return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function formatArgs(args) {
  if (!args || typeof args !== 'object') return '';
  return Object.entries(args)
    .map(([k, v]) => `${k}: ${v}`)
    .join(' · ');
}

function formatTime(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch { return iso; }
}

function relativeTime(iso) {
  if (!iso) return '';
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const s = Math.floor(diff / 1000);
    if (s < 60) return `${s}s ago`;
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}m ago`;
    return `${Math.floor(m / 60)}h ago`;
  } catch { return ''; }
}

function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// Refresh task list every 3s when there's a running task
setInterval(() => {
  if (allTasks.some(t => t.status === 'running')) {
    loadTaskHistory();
  }
}, 3000);
