/* ═══════════════════════════════════════════════════════════════════
   Voice Assistant — Frontend Application (SSE Streaming)
   ═══════════════════════════════════════════════════════════════════ */

'use strict';

// ── Recording state ─────────────────────────────────────────────────
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

// ── Confirmation state ───────────────────────────────────────────────
let activeConfirmationId = null;
let confirmationTimer = null;
let confirmationCountdown = 60;

// ── SSE abort controller ─────────────────────────────────────────────
let activeStreamController = null;

// ── DOM refs ─────────────────────────────────────────────────────────
const micBtn      = document.getElementById('mic-btn');
const uploadInput = document.getElementById('upload-input');
const statusText  = document.getElementById('status-text');

const sections = [
  'sec-transcript',
  'sec-accuracy',
  'sec-intent',
  'sec-entities',
  'sec-planner',
  'sec-execution',
  'sec-response',
];

// ══════════════════════════════════════════════════════════════════════
// Recording
// ══════════════════════════════════════════════════════════════════════

micBtn.addEventListener('click', async () => {
  if (isRecording) {
    stopRecording();
  } else {
    await startRecording();
  }
});

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
    audioChunks = [];

    mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunks.push(e.data); };
    mediaRecorder.onstop = () => {
      const blob = new Blob(audioChunks, { type: 'audio/webm' });
      showMicStatus('captured', 'Audio Captured');
      sendAudio(blob, 'recording.webm');
      stream.getTracks().forEach(t => t.stop());
    };

    mediaRecorder.start();
    isRecording = true;
    micBtn.textContent = 'Stop Recording';
    micBtn.classList.add('recording');
    statusText.textContent = '';
    showMicStatus('listening', 'Listening...');
    resetUI(/* keepMicStatus */ true);

  } catch (err) {
    statusText.textContent = 'Microphone access denied.';
  }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
  }
  isRecording = false;
  micBtn.textContent = 'Record Audio';
  micBtn.classList.remove('recording');
}

uploadInput.addEventListener('change', e => {
  const file = e.target.files[0];
  if (file) {
    resetUI();
    showMicStatus('captured', 'Audio Captured');
    sendAudio(file, file.name);
    uploadInput.value = '';
  }
});

// ══════════════════════════════════════════════════════════════════════
// UI reset helpers
// ══════════════════════════════════════════════════════════════════════

function resetUI(keepMicStatus = false) {
  // Cancel any active SSE stream
  if (activeStreamController) {
    activeStreamController.abort();
    activeStreamController = null;
  }

  hideAllSections();

  if (!keepMicStatus) clearMicStatus();

  const execDiv = document.getElementById('execution-val');
  if (execDiv) execDiv.innerHTML = '';
}

function hideAllSections() {
  sections.forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.className = 'section';
    }
    const badgeId = id.replace('sec-', 'badge-');
    const badgeEl = document.getElementById(badgeId);
    if (badgeEl) {
      badgeEl.className = 'stage-badge';
    }
    const hintId = id.replace('sec-', 'hint-');
    const hintEl = document.getElementById(hintId);
    if (hintEl) {
      hintEl.textContent = '';
    }
  });
}

function setSectionState(sectionId, state) {
  const sectionEl = document.getElementById(sectionId);
  if (!sectionEl) return;

  sectionEl.classList.remove('processing', 'completed', 'failed');
  if (state === 'processing') {
    sectionEl.classList.add('processing');
  } else if (state === 'completed') {
    sectionEl.classList.add('completed');
  } else if (state === 'failed') {
    sectionEl.classList.add('failed');
  }

  const badgeId = sectionId.replace('sec-', 'badge-');
  const badgeEl = document.getElementById(badgeId);
  if (badgeEl) {
    badgeEl.className = 'stage-badge';
    if (state === 'processing') {
      badgeEl.classList.add('working');
    } else if (state === 'completed') {
      badgeEl.classList.add('done');
    } else if (state === 'failed') {
      badgeEl.classList.add('fail');
    }
  }
}

function showProcessingHint(sectionId, text) {
  const hintId = sectionId.replace('sec-', 'hint-');
  const hintEl = document.getElementById(hintId);
  if (hintEl) {
    hintEl.textContent = text;
  }
}

function clearProcessingHint(sectionId) {
  const hintId = sectionId.replace('sec-', 'hint-');
  const hintEl = document.getElementById(hintId);
  if (hintEl) {
    hintEl.textContent = '';
  }
}

function revealSection(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add('visible');
}

// ══════════════════════════════════════════════════════════════════════
// Mic status badge
// ══════════════════════════════════════════════════════════════════════

function showMicStatus(state, text) {
  const el  = document.getElementById('mic-status');
  const txt = document.getElementById('mic-status-text');
  if (!el || !txt) return;
  el.className = `mic-status ${state}`;   // 'listening' or 'captured'
  txt.textContent = text;
}

function clearMicStatus() {
  const el = document.getElementById('mic-status');
  if (el) el.className = 'mic-status hidden';
}

// ══════════════════════════════════════════════════════════════════════
// SSE Audio submission & stream consumer
// ══════════════════════════════════════════════════════════════════════

async function sendAudio(blob, filename) {
  statusText.textContent = '';

  const formData = new FormData();
  formData.append('audio', blob, filename);

  // Abort any previous stream
  if (activeStreamController) activeStreamController.abort();
  activeStreamController = new AbortController();

  try {
    const res = await fetch('/transcribe_stream', {
      method: 'POST',
      body: formData,
      signal: activeStreamController.signal,
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
      statusText.textContent = 'Error: ' + (errData.error || 'Unknown error');
      return;
    }

    await consumeSSEStream(res.body);

  } catch (err) {
    if (err.name === 'AbortError') return; // user started a new recording
    statusText.textContent = 'Network error.';
  }
}

async function consumeSSEStream(body) {
  const reader  = body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    let boundary;
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const chunk = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);

      for (const line of chunk.split('\n')) {
        if (!line.startsWith('data: ')) continue;
        try {
          const event = JSON.parse(line.slice(6));
          handleSSEEvent(event);
        } catch (_) { /* malformed JSON — ignore */ }
      }
    }
  }
}

// ══════════════════════════════════════════════════════════════════════
// SSE event dispatcher
// ══════════════════════════════════════════════════════════════════════

function handleSSEEvent(event) {
  const { stage, status, data, message } = event;

  switch (stage) {

    // ── Transcript ──────────────────────────────────────────────────
    case 'transcript': {
      if (status === 'processing') {
        revealSection('sec-transcript');
        setSectionState('sec-transcript', 'processing');
        showProcessingHint('sec-transcript', 'Transcribing audio…');
        statusText.textContent = 'Transcribing…';

      } else if (status === 'completed') {
        clearProcessingHint('sec-transcript');
        setSectionState('sec-transcript', 'completed');
        populateTranscript(data);
        revealSection('sec-transcript');
        
        revealSection('sec-accuracy');
        setSectionState('sec-accuracy', 'completed');
        statusText.textContent = 'Transcript ready';
      }
      break;
    }

    // ── Intent ──────────────────────────────────────────────────────
    case 'intent': {
      if (status === 'processing') {
        revealSection('sec-intent');
        setSectionState('sec-intent', 'processing');
        showProcessingHint('sec-intent', 'Detecting intent…');
        statusText.textContent = 'Detecting intent…';

      } else if (status === 'completed') {
        clearProcessingHint('sec-intent');
        setSectionState('sec-intent', 'completed');
        const intentName = data.name || 'unknown';
        document.getElementById('intent-val').textContent = intentName;
        revealSection('sec-intent');
        statusText.textContent = 'Intent: ' + intentName;
      }
      break;
    }

    // ── Entities ────────────────────────────────────────────────────
    case 'entities': {
      if (status === 'processing') {
        revealSection('sec-entities');
        setSectionState('sec-entities', 'processing');
        showProcessingHint('sec-entities', 'Extracting entities…');
        statusText.textContent = 'Extracting entities…';

      } else if (status === 'completed') {
        clearProcessingHint('sec-entities');
        setSectionState('sec-entities', 'completed');
        populateEntities(data.entities);
        revealSection('sec-entities');
        statusText.textContent = 'Entities extracted';
      }
      break;
    }

    // ── Discovery ───────────────────────────────────────────────────
    case 'discovery': {
      if (status === 'processing') {
        statusText.textContent = 'Indexing system resources…';
      } else if (status === 'completed') {
        statusText.textContent = 'System context indexed';
      }
      break;
    }

    // ── Planner ─────────────────────────────────────────────────────
    case 'planner': {
      if (status === 'processing') {
        revealSection('sec-planner');
        setSectionState('sec-planner', 'processing');
        showProcessingHint('sec-planner', 'Building execution plan…');
        statusText.textContent = 'Planning…';

      } else if (status === 'completed') {
        clearProcessingHint('sec-planner');
        setSectionState('sec-planner', 'completed');
        document.getElementById('planner-val').innerHTML = syntaxHighlight(
          JSON.stringify(data || {}, null, 2)
        );
        revealSection('sec-planner');
        statusText.textContent = 'Plan ready';
      }
      break;
    }

    // ── Execution ───────────────────────────────────────────────────
    case 'execution': {
      if (status === 'processing' || status === 'running') {
        revealSection('sec-execution');
        setSectionState('sec-execution', 'processing');
        appendExecLogRow(message || '…', 'running');
        statusText.textContent = message || 'Executing…';

      } else if (status === 'completed') {
        setSectionState('sec-execution', 'completed');
        finaliseExecLog(data?.steps);
        statusText.textContent = 'Execution complete';

      } else if (status === 'requires_confirmation') {
        setSectionState('sec-execution', 'completed');
        appendExecLogRow(message || 'Awaiting confirmation…', 'confirm');
        revealSection('sec-execution');

      } else if (status === 'failed') {
        setSectionState('sec-execution', 'failed');
        appendExecLogRow(message || 'Execution failed', 'failure');
      }
      break;
    }

    // ── Response ────────────────────────────────────────────────────
    case 'response': {
      if (status === 'processing') {
        revealSection('sec-response');
        setSectionState('sec-response', 'processing');
        showProcessingHint('sec-response', 'Generating assistant response…');
        statusText.textContent = 'Generating response…';

      } else if (status === 'completed') {
        clearProcessingHint('sec-response');
        setSectionState('sec-response', 'completed');
        populateResponse(data);
        revealSection('sec-response');
      }
      break;
    }

    // ── Done ────────────────────────────────────────────────────────
    case 'done': {
      if (status === 'success') {
        clearMicStatus();
        statusText.textContent = 'Complete.';

      } else if (status === 'no_speech') {
        statusText.textContent = 'No speech detected.';
        populateResponse(data?.speech || { text: "I didn't catch that. Could you try again?" });
        revealSection('sec-response');
        setSectionState('sec-response', 'completed');
        clearMicStatus();

      } else if (status === 'requires_confirmation') {
        statusText.textContent = 'Awaiting confirmation…';
        renderConfirmationCard(data.confirmation);

      } else if (status === 'error') {
        statusText.textContent = 'Error: ' + (message || 'Unknown error');
        // Set all processing sections to failed
        sections.forEach(id => {
          const el = document.getElementById(id);
          if (el && el.classList.contains('processing')) {
            setSectionState(id, 'failed');
            clearProcessingHint(id);
          }
        });
        clearMicStatus();
      }
      break;
    }
  }
}

// ══════════════════════════════════════════════════════════════════════
// Execution log helpers
// ══════════════════════════════════════════════════════════════════════

function appendExecLogRow(text, type) {
  const execDiv = document.getElementById('execution-val');
  if (!execDiv) return;

  // Ignore confirmation payloads in row layout
  if (text.startsWith('__REQUIRES_CONFIRMATION__:')) return;

  const row = document.createElement('div');
  row.className = 'exec-log-row';

  let iconHtml = '';
  let textClass = '';

  if (type === 'running') {
    iconHtml = '<span class="exec-log-icon">⟳</span>';
  } else if (type === 'confirm') {
    iconHtml = '<span class="exec-log-icon">⚠</span>';
  } else if (type === 'success') {
    iconHtml = '<span class="exec-log-icon">✓</span>';
    textClass = 'success';
  } else if (type === 'failure') {
    iconHtml = '<span class="exec-log-icon">✗</span>';
    textClass = 'failure';
  } else {
    iconHtml = '<span class="exec-log-icon">·</span>';
  }

  if (text.startsWith('Step ')) {
    textClass = 'step-label';
    iconHtml = '<span class="exec-log-icon">➔</span>';
  }

  row.innerHTML = `${iconHtml}<span class="exec-log-text ${textClass}">${escapeHtml(text)}</span>`;
  execDiv.appendChild(row);
}

function finaliseExecLog(steps) {
  const execDiv = document.getElementById('execution-val');
  if (!execDiv) return;

  // Update all ongoing step spinner icons to done
  const rows = execDiv.querySelectorAll('.exec-log-row');
  rows.forEach(row => {
    const iconEl = row.querySelector('.exec-log-icon');
    const textEl = row.querySelector('.exec-log-text');
    if (iconEl && iconEl.textContent === '⟳') {
      iconEl.textContent = '✓';
      if (textEl) {
        textEl.className = 'exec-log-text success';
      }
    }
  });

  // Final completion row
  appendExecLogRow('Execution completed', 'success');
}

// ══════════════════════════════════════════════════════════════════════
// Populate helpers
// ══════════════════════════════════════════════════════════════════════

function populateTranscript(data) {
  document.getElementById('transcript-val').textContent =
    data.text || 'No speech detected.';

  if (data.stt) {
    document.getElementById('met-model').textContent =
      (data.stt.model || '').split('/').pop();
    document.getElementById('met-conf').textContent =
      data.stt.confidence + '%';
    document.getElementById('met-time').textContent =
      data.stt.processing_time_ms + 'ms';
  }
}

function populateEntities(entities) {
  const entGrid = document.getElementById('entities-val');
  entGrid.innerHTML = '';
  if (entities && Object.keys(entities).length > 0) {
    for (const [k, v] of Object.entries(entities)) {
      entGrid.innerHTML +=
        `<span class="entity-k">${escapeHtml(k)}</span>` +
        `<span class="entity-v">${escapeHtml(String(v))}</span>`;
    }
  } else {
    entGrid.innerHTML =
      `<span class="entity-k">none</span><span class="entity-v">-</span>`;
  }
}

function populateResponse(data) {
  if (!data) return;
  const text = data.text || '';
  document.getElementById('response-text').textContent = text;
  const player = document.getElementById('audio-player');
  if (data.audio_url) {
    player.src = data.audio_url;
    player.style.display = 'block';
    setTimeout(() => player.play().catch(() => { }), 300);
  } else {
    player.style.display = 'none';
  }
}

// ══════════════════════════════════════════════════════════════════════
// Full-data populate (used by confirmation resume + legacy path)
// ══════════════════════════════════════════════════════════════════════

function populateData(data) {
  // Transcript
  document.getElementById('transcript-val').textContent =
    data.transcription || 'No speech detected.';

  // Accuracy
  if (data.stt) {
    document.getElementById('met-model').textContent =
      (data.stt.model || '').split('/').pop();
    document.getElementById('met-conf').textContent =
      data.stt.confidence + '%';
    document.getElementById('met-time').textContent =
      data.stt.processing_time_ms + 'ms';
  }

  // Intent
  document.getElementById('intent-val').textContent =
    data.intent ? data.intent.name : 'unknown';

  // Entities
  populateEntities(data.entities);

  // Planner
  document.getElementById('planner-val').innerHTML =
    syntaxHighlight(JSON.stringify(data.planner || {}, null, 2));

  // Execution
  const execDiv = document.getElementById('execution-val');
  execDiv.innerHTML = '';
  if (data.execution && data.execution.length > 0) {
    data.execution.forEach(step => {
      const type = step.success ? 'success' : 'failure';
      const icon = step.success ? '✓' : '✗';
      const row = document.createElement('div');
      row.className = 'exec-log-row';
      row.innerHTML =
        `<span class="exec-log-icon">${icon}</span>` +
        `<span class="exec-log-text ${type}">` +
        `${escapeHtml(step.tool || 'unknown')}: ${escapeHtml(step.message || '')}` +
        `</span>`;
      execDiv.appendChild(row);
    });
  } else {
    execDiv.textContent = 'No actions executed.';
  }

  // Response
  if (data.speech) {
    populateResponse(data.speech);
    const player = document.getElementById('audio-player');
    if (data.speech.audio_url) {
      setTimeout(() => player.play().catch(() => console.log('Autoplay blocked')), 2100);
    }
  }
}

function revealSequentially() {
  let delay = 0;
  sections.forEach(id => {
    setTimeout(() => {
      document.getElementById(id).classList.add('visible');
    }, delay);
    delay += 300;
  });
}

// ══════════════════════════════════════════════════════════════════════
// Confirmation Card
// ══════════════════════════════════════════════════════════════════════

function renderConfirmationCard(confirmation) {
  const card       = document.getElementById('confirmation-card');
  const messageEl  = document.getElementById('confirm-message');
  const detailsEl  = document.getElementById('confirm-details');
  const proceedBtn = document.getElementById('btn-proceed');
  const cancelBtn  = document.getElementById('btn-cancel');

  activeConfirmationId = confirmation.id;
  messageEl.textContent  = confirmation.message;
  detailsEl.innerHTML    = buildConfirmDetails(confirmation);
  proceedBtn.textContent = getConfirmButtonLabel(confirmation.tool);
  cancelBtn.textContent  = 'Cancel';

  card.style.display = '';
  card.classList.remove('fading-out');

  const remaining = confirmation.remaining_seconds || 60;
  startConfirmationTimer(remaining);
  attachConfirmationListeners();
}

function buildConfirmDetails(confirmation) {
  const tool = confirmation.tool || '';
  const args = confirmation.args || {};

  if (tool === 'send_whatsapp_message' || tool === 'type_message') {
    let html = '';
    if (args.contact) {
      html += `<div class="confirm-detail-row">
        <span class="confirm-detail-label">Contact</span>
        <span class="confirm-detail-value">${escapeHtml(args.contact)}</span>
      </div>`;
    }
    if (args.message) {
      html += `<div class="confirm-detail-row">
        <span class="confirm-detail-label">Message</span>
        <span class="confirm-detail-value">${escapeHtml(args.message)}</span>
      </div>`;
    }
    return html || '';
  }

  if (tool === 'delete_file' || tool === 'delete_folder') {
    const path = args.path || args.filename || 'unknown';
    return `<div class="confirm-detail-row">
      <span class="confirm-detail-label">Path</span>
      <span class="confirm-detail-value">${escapeHtml(path)}</span>
    </div>`;
  }

  if (tool === 'shutdown_system' || tool === 'reboot_system') {
    return '';
  }

  if (tool === 'execute_shell') {
    const cmd = args.command || args.cmd || '';
    return `<div class="confirm-detail-row">
      <span class="confirm-detail-label">Command</span>
      <span class="confirm-detail-value">${escapeHtml(cmd)}</span>
    </div>`;
  }

  let html = '';
  for (const [k, v] of Object.entries(args)) {
    html += `<div class="confirm-detail-row">
      <span class="confirm-detail-label">${escapeHtml(k)}</span>
      <span class="confirm-detail-value">${escapeHtml(String(v))}</span>
    </div>`;
  }
  return html;
}

function getConfirmButtonLabel(tool) {
  const labels = {
    'send_whatsapp_message': 'Send Message',
    'type_message':          'Send Message',
    'delete_file':           'Delete',
    'delete_folder':         'Delete',
    'shutdown_system':       'Shutdown',
    'reboot_system':         'Reboot',
    'execute_shell':         'Execute',
  };
  return labels[tool] || 'Proceed';
}

function hideConfirmationCard() {
  const card = document.getElementById('confirmation-card');
  card.classList.add('fading-out');

  if (confirmationTimer) {
    clearInterval(confirmationTimer);
    confirmationTimer = null;
  }
  activeConfirmationId = null;

  setTimeout(() => {
    card.style.display = 'none';
    card.classList.remove('fading-out');
  }, 350);
}

function attachConfirmationListeners() {
  const proceedBtn = document.getElementById('btn-proceed');
  const cancelBtn  = document.getElementById('btn-cancel');

  const newProceed = proceedBtn.cloneNode(true);
  const newCancel  = cancelBtn.cloneNode(true);
  proceedBtn.parentNode.replaceChild(newProceed, proceedBtn);
  cancelBtn.parentNode.replaceChild(newCancel, cancelBtn);

  newProceed.addEventListener('click', () => sendConfirmation('proceed'));
  newCancel.addEventListener('click',  () => sendConfirmation('cancel'));
}

async function sendConfirmation(decision) {
  if (!activeConfirmationId) return;

  const confirmId  = activeConfirmationId;
  const proceedBtn = document.getElementById('btn-proceed');
  const cancelBtn  = document.getElementById('btn-cancel');
  proceedBtn.disabled = true;
  cancelBtn.disabled  = true;
  proceedBtn.style.opacity = '0.6';
  cancelBtn.style.opacity  = '0.6';

  statusText.textContent = decision === 'proceed' ? 'Executing…' : 'Cancelling…';

  try {
    const res = await fetch('/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        confirmation_id: confirmId,
        decision: decision,
      }),
    });

    const data = await res.json();

    hideConfirmationCard();

    statusText.textContent = data.success
      ? 'Complete.'
      : 'Action completed with issues.';

    document.getElementById('response-text').textContent =
      data.message || (decision === 'cancel' ? 'Action cancelled.' : 'Done.');

    const player = document.getElementById('audio-player');
    if (data.speech && data.speech.audio_url) {
      player.src = data.speech.audio_url;
      player.style.display = 'block';
      setTimeout(() => player.play().catch(() => { }), 300);
    } else {
      player.style.display = 'none';
    }

    document.getElementById('sec-response').classList.add('visible');

  } catch (err) {
    hideConfirmationCard();
    statusText.textContent = 'Network error during confirmation.';
  }
}

function startConfirmationTimer(seconds) {
  if (confirmationTimer) clearInterval(confirmationTimer);

  confirmationCountdown = seconds;
  const totalSeconds = seconds;
  const timerText = document.getElementById('confirm-timer-text');
  const timerFill = document.getElementById('confirm-timer-fill');

  timerText.textContent = `${confirmationCountdown}s`;
  timerFill.style.width = `${(confirmationCountdown / totalSeconds) * 100}%`;

  confirmationTimer = setInterval(() => {
    confirmationCountdown--;

    if (confirmationCountdown <= 0) {
      clearInterval(confirmationTimer);
      confirmationTimer = null;

      timerText.textContent = 'Timed out';
      timerFill.style.width = '0%';
      statusText.textContent = 'Confirmation timed out.';

      setTimeout(() => {
        hideConfirmationCard();
        if (activeConfirmationId) {
          fetch('/confirm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              confirmation_id: activeConfirmationId,
              decision: 'cancel',
            }),
          }).catch(() => { });
        }
      }, 1000);
      return;
    }

    timerText.textContent = `${confirmationCountdown}s`;
    timerFill.style.width = `${(confirmationCountdown / totalSeconds) * 100}%`;
  }, 1000);
}

// ══════════════════════════════════════════════════════════════════════
// Page Load: Check for pending confirmations (survives refresh)
// ══════════════════════════════════════════════════════════════════════

async function checkPendingConfirmation() {
  try {
    const res  = await fetch('/pending');
    const data = await res.json();
    if (data.confirmation) {
      statusText.textContent = 'Pending confirmation restored.';
      renderConfirmationCard(data.confirmation);
    }
  } catch (_) {
    // Silently ignore — no pending confirmation
  }
}

checkPendingConfirmation();

// ══════════════════════════════════════════════════════════════════════
// Utilities
// ══════════════════════════════════════════════════════════════════════

function syntaxHighlight(json) {
  return json.replace(
    /("(\\u[\da-fA-F]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g,
    match => {
      let cls = 'json-number';
      if (/^"/.test(match)) {
        cls = /:$/.test(match) ? 'json-key' : 'json-string';
      } else if (/true|false/.test(match)) cls = 'json-boolean';
      else if (/null/.test(match)) cls = 'json-null';
      return '<span class="' + cls + '">' + match + '</span>';
    }
  );
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}
