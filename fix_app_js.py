import re

with open('web/static/js/app.js', 'r', encoding='utf-8') as f:
    content = f.read()

# The tool inserted our block near line 743. Let's remove it if it's there.
chunk_to_remove = r"// File Search Modal logic.*?\}\s+async function simulateUserCommand\(text\) \{.*?\}\s*"
content = re.sub(chunk_to_remove, '', content, flags=re.DOTALL)

# Now safely append it to the absolute end of the file.
to_append = """
// File Search Modal logic
function showFileSearchModal(results) {
  const modal = document.getElementById('file-search-modal');
  const resultsContainer = document.getElementById('file-search-results');
  const actionsContainer = document.getElementById('file-search-actions');
  
  if (!modal || !resultsContainer || !actionsContainer) return;
  
  resultsContainer.innerHTML = '';
  actionsContainer.innerHTML = '';
  
  results.forEach((res, index) => {
    const num = index + 1;
    const div = document.createElement('div');
    div.style.padding = '12px';
    div.style.border = '1px solid var(--border, #eee)';
    div.style.borderRadius = '8px';
    div.style.background = '#fafafa';
    
    div.innerHTML = `
      <div style="font-weight: 600; color: var(--primary, #007bff); cursor: pointer;" onclick="simulateUserCommand('Open number ${num}')">${num}. ${res.filename}</div>
      <div style="font-size: 0.85rem; color: #555; margin-top: 4px;">Folder: ${res.folder_path || res.folder}</div>
      <div style="font-size: 0.85rem; color: #555;">Modified: ${res.modified_date || (res.modified_ts ? new Date(res.modified_ts * 1000).toDateString() : 'N/A')}</div>
      <div style="font-size: 0.85rem; color: #555;">Confidence: ${res.confidence || (res.score ? Math.round(res.score * 100) + '%' : 'N/A')}</div>
    `;
    resultsContainer.appendChild(div);
    
    const btn = document.createElement('button');
    btn.className = 'btn btn-primary';
    btn.style.padding = '6px 12px';
    btn.style.fontSize = '0.85rem';
    btn.textContent = `Open number ${num}`;
    btn.onclick = () => {
      modal.style.display = 'none';
      simulateUserCommand(`Open number ${num}`);
    };
    actionsContainer.appendChild(btn);
  });
  
  const cancelBtn = document.createElement('button');
  cancelBtn.className = 'btn btn-cancel-action';
  cancelBtn.style.padding = '6px 12px';
  cancelBtn.style.fontSize = '0.85rem';
  cancelBtn.textContent = 'Cancel';
  cancelBtn.onclick = () => {
    modal.style.display = 'none';
  };
  actionsContainer.appendChild(cancelBtn);

  modal.style.display = 'flex';
}

async function simulateUserCommand(text) {
  try {
    const formData = new FormData();
    formData.append('text', text);
    const res = await fetch('/transcribe_stream', { method: 'POST', body: formData });
    if (res.ok) await consumeSSEStream(res.body);
  } catch(e) {
    console.error(e);
  }
}
"""

if 'showFileSearchModal' not in content:
    content += to_append

with open('web/static/js/app.js', 'w', encoding='utf-8') as f:
    f.write(content)
