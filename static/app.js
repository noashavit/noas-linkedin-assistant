/* ── State ──────────────────────────────────────────────────────────────── */
let fullText = '';

/* ── Boot ───────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  loadModels();
  checkSession();
});

async function loadModels() {
  const sel = document.getElementById('model-select');
  try {
    const res = await fetch('/api/models');
    if (!res.ok) throw new Error(await res.text());
    const { models } = await res.json();
    if (models.length) {
      sel.innerHTML = models.map(m => `<option value="${m}">${m}</option>`).join('');
    } else {
      sel.innerHTML = '<option value="">No models found — is Ollama running?</option>';
    }
  } catch {
    sel.innerHTML = '<option value="">Cannot reach Ollama</option>';
  }
}

/* ── Session ────────────────────────────────────────────────────────────── */
async function checkSession() {
  const dot   = document.getElementById('session-dot');
  const label = document.getElementById('session-label');
  try {
    const res  = await fetch('/api/session');
    const data = await res.json();
    if (data.connected) {
      dot.className   = 'session-dot connected';
      label.textContent = 'LinkedIn connected';
    } else {
      dot.className   = 'session-dot disconnected';
      label.textContent = 'Connect LinkedIn';
    }
  } catch {
    dot.className   = 'session-dot disconnected';
    label.textContent = 'Connect LinkedIn';
  }
}

async function handleSessionClick() {
  const dot   = document.getElementById('session-dot');
  const label = document.getElementById('session-label');

  dot.className   = 'session-dot';
  label.textContent = 'Opening browser…';

  try {
    // This call blocks until the user logs in (server-side wait)
    const res = await fetch('/api/login', { method: 'POST' });
    if (res.ok) {
      dot.className   = 'session-dot connected';
      label.textContent = 'LinkedIn connected';
    } else {
      const err = await res.json();
      dot.className   = 'session-dot disconnected';
      label.textContent = 'Login failed';
      alert(`Login error: ${err.detail}`);
    }
  } catch (e) {
    dot.className   = 'session-dot disconnected';
    label.textContent = 'Connect LinkedIn';
    alert(`Error: ${e.message}`);
  }
}

/* ── Analysis entry point ───────────────────────────────────────────────── */
async function startAnalysis() {
  const originUrl = document.getElementById('origin-url').value.trim();
  const destUrl   = document.getElementById('dest-url').value.trim();
  const model     = document.getElementById('model-select').value;

  if (!originUrl || !destUrl) { alert('Enter both LinkedIn profile URLs.'); return; }
  if (!model) { alert('Select a model. Make sure Ollama is running.'); return; }

  resetUI();
  fullText = '';

  setBtn(true);
  show('status-section');

  try {
    const res = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ origin_url: originUrl, destination_url: destUrl, model }),
    });

    if (!res.ok) {
      addStatus(`Server error: ${res.status}`, 'warn');
      setBtn(false);
      return;
    }

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let   buf     = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });

      const lines = buf.split('\n');
      buf = lines.pop(); // hold incomplete line

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try { handleEvent(JSON.parse(line.slice(6))); }
          catch { /* ignore malformed */ }
        }
      }
    }
  } catch (err) {
    addStatus(`Connection error: ${err.message}`, 'warn');
    setBtn(false);
  }
}

/* ── Event handler ──────────────────────────────────────────────────────── */
function handleEvent(ev) {
  switch (ev.type) {
    case 'status':
      addStatus(ev.message, ev.message.startsWith('⚠️') ? 'warn' : 'active');
      break;

    case 'profiles':
      showProfilesBar(ev.origin, ev.destination);
      show('stream-section');
      break;

    case 'token':
      fullText += ev.content;
      appendStream(ev.content);
      break;

    case 'done':
      finaliseResults(fullText);
      doneStatus();
      setBtn(false);
      break;

    case 'error':
      addStatus(`⚠️  ${ev.message}`, 'warn');
      setBtn(false);
      break;
  }
}

/* ── Status log ─────────────────────────────────────────────────────────── */
function addStatus(msg, state = 'active') {
  const log = document.getElementById('status-log');
  // dim previous active items
  log.querySelectorAll('.active').forEach(el => {
    el.classList.replace('active', 'done');
  });
  const el = document.createElement('div');
  el.className = `status-item ${state}`;
  el.textContent = `→ ${msg}`;
  log.appendChild(el);
}

function doneStatus() {
  document.querySelectorAll('.status-item.active').forEach(el =>
    el.classList.replace('active', 'done')
  );
}

/* ── Live stream output ─────────────────────────────────────────────────── */
function appendStream(token) {
  const pre = document.getElementById('stream-output');
  pre.textContent += token;
  // auto-scroll to bottom
  pre.scrollTop = pre.scrollHeight;
}

/* ── Profiles bar ───────────────────────────────────────────────────────── */
function showProfilesBar(origin, dest) {
  document.getElementById('profiles-bar').innerHTML = `
    <div class="profile-chip">You: <strong>${esc(origin.name)}</strong></div>
    <span class="sep">→</span>
    <div class="profile-chip">Them: <strong>${esc(dest.name)}</strong></div>
  `;
}

/* ── Parse + render results ─────────────────────────────────────────────── */
function finaliseResults(text) {
  const sections = parseSections(text);

  // Insight cards
  fillCard('tone-body',        'card-tone',        sections['TONE ANALYSIS']);
  fillCard('insights-body',    'card-insights',     sections['DESTINATION INSIGHTS']);
  fillCard('connections-body', 'card-connections',  sections['CONNECTION POINTS']);
  fillCard('strategy-body',    'card-strategy',     sections['OUTREACH STRATEGY']);

  // Drafts
  renderDrafts('linkedin-drafts', parseDrafts(sections['LINKEDIN DRAFTS'] || ''), false);
  renderDrafts('email-drafts',    parseDrafts(sections['EMAIL DRAFTS']    || ''), true);

  hide('stream-section');
  show('results-section');
}

function fillCard(bodyId, cardId, text) {
  if (!text) return;
  document.getElementById(bodyId).textContent = text.trim();
  document.getElementById(cardId).classList.add('visible');
}

/* ── Section parser ─────────────────────────────────────────────────────── */
function parseSections(text) {
  const out  = {};
  const lines = text.split('\n');
  let key = null, buf = [];

  for (const line of lines) {
    const m = line.match(/^##\s+(.+)$/);
    if (m) {
      if (key) out[key] = buf.join('\n');
      key = m[1].trim();
      buf = [];
    } else if (key) {
      buf.push(line);
    }
  }
  if (key) out[key] = buf.join('\n');
  return out;
}

/* ── Draft parser ───────────────────────────────────────────────────────── */
function parseDrafts(text) {
  const parts = text.split(/###\s*Draft\s*\d+/i);
  return parts.slice(1).map(s => s.trim()).filter(Boolean);
}

/* ── Draft renderer ─────────────────────────────────────────────────────── */
function renderDrafts(containerId, drafts, isEmail) {
  const container = document.getElementById(containerId);
  if (!container || !drafts.length) return;
  container.innerHTML = '';

  drafts.forEach((draft, i) => {
    const card = document.createElement('div');
    card.className = 'draft-card';

    // Number
    const num = document.createElement('div');
    num.className = 'draft-num';
    num.textContent = i + 1;

    // Body
    const body = document.createElement('div');
    body.className = 'draft-body';

    if (isEmail) {
      const lines       = draft.split('\n');
      const subjectLine = lines.find(l => /^subject:/i.test(l.trim()));
      const bodyLines   = lines.filter(l => !/^subject:/i.test(l.trim())).join('\n').trim();

      if (subjectLine) {
        const subj = document.createElement('span');
        subj.className = 'email-subject';
        subj.textContent = subjectLine.replace(/^subject:\s*/i, '').trim();
        body.appendChild(subj);
      }
      const bodyText = document.createElement('span');
      bodyText.textContent = bodyLines;
      body.appendChild(bodyText);
    } else {
      body.textContent = draft;
    }

    // Copy button
    const btn = document.createElement('button');
    btn.className = 'copy-btn';
    btn.textContent = 'Copy';
    btn.addEventListener('click', () => copyText(draft, btn));

    card.append(num, body, btn);
    container.appendChild(card);

    // Stagger entrance animation
    requestAnimationFrame(() =>
      setTimeout(() => card.classList.add('visible'), i * 70)
    );
  });
}

/* ── Copy helper ────────────────────────────────────────────────────────── */
async function copyText(text, btn) {
  try {
    await navigator.clipboard.writeText(text);
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(() => {
      btn.textContent = 'Copy';
      btn.classList.remove('copied');
    }, 2000);
  } catch {
    btn.textContent = 'Error';
  }
}

/* ── UI helpers ─────────────────────────────────────────────────────────── */
function resetUI() {
  // Clear status log
  document.getElementById('status-log').innerHTML = '';

  // Clear stream
  document.getElementById('stream-output').textContent = '';

  // Clear results
  ['tone-body', 'insights-body', 'connections-body', 'strategy-body'].forEach(id => {
    document.getElementById(id).textContent = '';
  });
  ['card-tone', 'card-insights', 'card-connections', 'card-strategy'].forEach(id => {
    document.getElementById(id).classList.remove('visible');
  });
  document.getElementById('linkedin-drafts').innerHTML = '';
  document.getElementById('email-drafts').innerHTML   = '';
  document.getElementById('profiles-bar').innerHTML   = '';

  hide('stream-section');
  hide('results-section');
}

function setBtn(loading) {
  const btn = document.getElementById('analyze-btn');
  btn.disabled = loading;
  btn.innerHTML = loading
    ? 'Analyzing… <span class="arrow">⋯</span>'
    : 'Analyze <span class="arrow">→</span>';
}

function show(id) { document.getElementById(id).classList.remove('hidden'); }
function hide(id) { document.getElementById(id).classList.add('hidden'); }

function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}
