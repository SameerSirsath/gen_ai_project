/**
 * main.js — High-End SaaS Client Logic & AJAX Interactions
 * Powers SweetAlert2 alerts, loading spinners, API Key management,
 * Lead Context NLP processing, AI Agent email generation, and SMTP dispatch.
 */

// ──────────────── Global Toast & Alert Helpers ────────────────
const Toast = Swal.mixin({
  toast: true,
  position: 'top-end',
  showConfirmButton: false,
  timer: 3000,
  timerProgressBar: true,
  didOpen: (toast) => {
    toast.addEventListener('mouseenter', Swal.stopTimer);
    toast.addEventListener('mouseleave', Swal.resumeTimer);
  }
});

function showToast(message, isError = false) {
  Toast.fire({
    icon: isError ? 'error' : 'success',
    title: message,
    background: '#FFFFFF',
    color: '#1B264F',
    iconColor: isError ? '#EF4444' : '#00B4A0'
  });
}

function showModalAlert(title, text, icon = 'success') {
  return Swal.fire({
    title: title,
    text: text,
    icon: icon,
    confirmButtonColor: '#00B4A0',
    background: '#FFFFFF',
    customClass: {
      popup: 'rounded-4 shadow-lg',
      confirmButton: 'btn-teal px-4'
    }
  });
}

// ──────────────── Button Loading State Helper ────────────────
function setButtonLoading(button, isLoading, loadingText = 'Processing...') {
  if (!button) return;
  if (isLoading) {
    button.dataset.originalHtml = button.innerHTML;
    button.disabled = true;
    button.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>${loadingText}`;
  } else {
    button.disabled = false;
    button.innerHTML = button.dataset.originalHtml || 'Submit';
  }
}

// ──────────────── Sidebar Mobile Toggle ────────────────
document.addEventListener('DOMContentLoaded', () => {
  const sidebarToggleBtn = document.getElementById('sidebarToggleBtn');
  const sidebar = document.querySelector('.sidebar');
  if (sidebarToggleBtn && sidebar) {
    sidebarToggleBtn.addEventListener('click', () => {
      sidebar.classList.toggle('show');
    });
  }

  // Initialize AOS if available
  if (typeof AOS !== 'undefined') {
    AOS.init({
      duration: 800,
      once: true,
      offset: 50
    });
  }
});

// ──────────────── 1. API Keys Management ────────────────
async function loadApiKeys() {
  const tableBody = document.getElementById('apiKeysTableBody');
  if (!tableBody) return;

  try {
    const res = await fetch('/api/keys');
    if (!res.ok) throw new Error('Failed to load keys.');
    const keys = await res.json();

    if (keys.length === 0) {
      tableBody.innerHTML = `
        <tr>
          <td colspan="5" class="text-center py-4 text-muted">
            <i class="fa-solid fa-key text-secondary mb-2 fs-3 d-block"></i>
            No API keys stored yet. Click "+ Add Key" to configure Groq or Gemini.
          </td>
        </tr>`;
      return;
    }

    tableBody.innerHTML = keys.map(k => `
      <tr>
        <td>
          <span class="badge ${k.provider.toLowerCase() === 'groq' ? 'bg-primary' : 'bg-success'} text-white px-3 py-2 rounded-pill">
            <i class="fa-solid fa-microchip me-1"></i> ${k.provider.toUpperCase()}
          </span>
        </td>
        <td class="fw-semibold text-dark">${k.key_alias}</td>
        <td><code class="text-secondary bg-light px-2 py-1 rounded">${k.key_value}</code></td>
        <td>
          <div class="form-check form-switch">
            <input class="form-check-input" type="checkbox" role="switch" id="toggle-${k.id}" ${k.is_active ? 'checked' : ''} onchange="toggleKeyStatus(${k.id}, this.checked)">
            <label class="form-check-label text-muted small" for="toggle-${k.id}">${k.is_active ? 'Active' : 'Inactive'}</label>
          </div>
        </td>
        <td>
          <button class="btn btn-sm btn-outline-danger rounded-pill px-3" onclick="deleteApiKey(${k.id})">
            <i class="fa-solid fa-trash-can me-1"></i> Delete
          </button>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    showToast(err.message, true);
  }
}

async function handleAddKeySubmit(event) {
  event.preventDefault();
  const form = event.target;
  const btn = form.querySelector('button[type="submit"]');
  const provider = document.getElementById('keyProvider').value;
  const alias = document.getElementById('keyAlias').value.trim();
  const value = document.getElementById('keyValue').value.trim();

  if (!alias || !value) {
    showToast('Please fill out all fields.', true);
    return;
  }

  setButtonLoading(btn, true, 'Saving Key...');
  try {
    const res = await fetch('/api/keys', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider, key_alias: alias, key_value: value })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to save key.');

    showToast('API Key saved and encrypted securely!');
    form.reset();
    const modalEl = document.getElementById('addKeyModal');
    if (modalEl) {
      const modal = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
      modal.hide();
    }
    loadApiKeys();
  } catch (err) {
    showToast(err.message, true);
  } finally {
    setButtonLoading(btn, false);
  }
}

async function deleteApiKey(keyId) {
  const result = await Swal.fire({
    title: 'Delete this API Key?',
    text: 'This will permanently remove the encrypted key from MySQL.',
    icon: 'warning',
    showCancelButton: true,
    confirmButtonColor: '#EF4444',
    cancelButtonColor: '#64748B',
    confirmButtonText: 'Yes, delete',
    background: '#FFFFFF',
    customClass: { popup: 'rounded-4 shadow-lg' }
  });

  if (result.isConfirmed) {
    try {
      const res = await fetch(`/api/keys/${keyId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Failed to delete key.');
      showToast('Key deleted successfully.');
      loadApiKeys();
    } catch (err) {
      showToast(err.message, true);
    }
  }
}

async function toggleKeyStatus(keyId, isActive) {
  try {
    const res = await fetch(`/api/keys/${keyId}/toggle`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_active: isActive })
    });
    if (!res.ok) throw new Error('Failed to update status.');
    showToast(`Key set to ${isActive ? 'Active' : 'Inactive'}.`);
  } catch (err) {
    showToast(err.message, true);
    loadApiKeys();
  }
}

// ──────────────── 2. Company Profile Sync ────────────────
async function handleCompanyProfileSubmit(event) {
  event.preventDefault();
  const form = event.target;
  const btn = document.getElementById('saveCompanyBtn') || form.querySelector('button[type="submit"]');

  const payload = {
    name: document.getElementById('companyName').value.trim(),
    industry: document.getElementById('companyIndustry').value.trim(),
    value_proposition: document.getElementById('valueProposition').value.trim(),
    services_offered: document.getElementById('servicesOffered').value.trim(),
    case_studies: document.getElementById('caseStudies').value.trim(),
  };

  setButtonLoading(btn, true, 'Syncing to Vector DB...');
  try {
    const res = await fetch('/api/company', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok || !data.success) throw new Error(data.error || 'Failed to update company profile.');

    showModalAlert(
      'Profile Synced!',
      'Company profile details and embeddings were updated in MySQL and ChromaDB vector store.',
      'success'
    );
  } catch (err) {
    showToast(err.message, true);
  } finally {
    setButtonLoading(btn, false);
  }
}

// ──────────────── 3. Leads Creation ────────────────
async function handleCreateLead(event, mode) {
  event.preventDefault();
  const form = event.target;
  const btn = form.querySelector('button[type="submit"]');

  let payload = { mode: mode };
  if (mode === 'Auto') {
    payload.company_name = document.getElementById('autoCompanyName').value.trim() || 'Scraped Company';
    payload.website_url = document.getElementById('autoWebsiteUrl').value.trim();
    if (!payload.website_url) {
      showToast('Website URL is required.', true);
      return;
    }
  } else {
    payload.company_name = document.getElementById('manualCompanyName').value.trim();
    payload.contact_name = document.getElementById('manualContactName').value.trim();
    payload.email = document.getElementById('manualEmail').value.trim();
    payload.website_url = document.getElementById('manualWebsite').value.trim();
    payload.raw_text = document.getElementById('manualRawText').value.trim();
    if (!payload.company_name) {
      showToast('Company Name is required.', true);
      return;
    }
  }

  setButtonLoading(btn, true, mode === 'Auto' ? 'Scraping & Ingesting...' : 'Creating Lead...');
  try {
    const res = await fetch('/api/leads', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok || !data.success) throw new Error(data.error || 'Failed to create lead.');

    showToast('Lead created successfully!');
    const modalEl = document.getElementById('addLeadModal');
    if (modalEl) {
      const modal = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
      modal.hide();
    }
    setTimeout(() => {
      window.location.reload();
    }, 1000);
  } catch (err) {
    showToast(err.message, true);
  } finally {
    setButtonLoading(btn, false);
  }
}

// ──────────────── 4. AI Agent Workspace (NLP, Generation, SMTP) ────────────────
async function syncLeadContextToChroma(leadId) {
  const rawTextEl = document.getElementById('workspaceRawText');
  const btn = document.getElementById('syncVectorBtn');
  const rawText = rawTextEl ? rawTextEl.value.trim() : '';

  if (!rawText) {
    showToast('Please enter or select raw text before syncing.', true);
    return;
  }

  setButtonLoading(btn, true, 'Running NLP & Syncing Chroma...');
  try {
    const res = await fetch(`/api/leads/${leadId}/process`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw_text: rawText, source_type: 'Manual' })
    });
    const data = await res.json();
    if (!res.ok || data.status !== 'success') throw new Error(data.error || 'Chroma sync failed.');

    // Update UI with extracted keywords
    const keywordsBadgeContainer = document.getElementById('extractedKeywordsContainer');
    if (keywordsBadgeContainer && data.keywords) {
      keywordsBadgeContainer.innerHTML = data.keywords.map(kw => `
        <span class="badge bg-light text-dark border me-1 mb-1 p-2">
          <i class="fa-solid fa-tag text-teal me-1"></i>${kw}
        </span>
      `).join('');
    }

    showModalAlert(
      'NLP Sync Complete!',
      `Text cleaned and chunked into ${data.chunks_created} vectors in ChromaDB (cosine space).`,
      'success'
    );
  } catch (err) {
    showToast(err.message, true);
  } finally {
    setButtonLoading(btn, false);
  }
}

async function generateAIEmail(leadId) {
  const btn = document.getElementById('generateEmailBtn');
  const outputPlaceholder = document.getElementById('outputPlaceholder');
  const outputContent = document.getElementById('outputContent');
  const emailSubjectInput = document.getElementById('emailSubject');
  const emailBodyInput = document.getElementById('emailBody');
  const evaluatorBadge = document.getElementById('evaluatorBadge');
  const evaluatorReason = document.getElementById('evaluatorReasoning');
  const sendEmailBtn = document.getElementById('sendEmailBtn');

  setButtonLoading(btn, true, 'Multi-Agent Thinking...');
  if (outputPlaceholder) outputPlaceholder.classList.remove('d-none');
  if (outputContent) outputContent.classList.add('d-none');

  try {
    const res = await fetch(`/api/leads/${leadId}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    const data = await res.json();
    if (!res.ok || !data.success) throw new Error(data.error || 'Email generation failed.');

    if (outputPlaceholder) outputPlaceholder.classList.add('d-none');
    if (outputContent) outputContent.classList.remove('d-none');

    const email = data.email || {};
    if (emailSubjectInput) emailSubjectInput.value = email.subject || '';
    if (emailBodyInput) emailBodyInput.value = email.body || '';

    const score = parseFloat(email.evaluator_score || 1.0);
    const passed = score >= 0.7;

    if (evaluatorBadge) {
      if (passed) {
        evaluatorBadge.className = 'badge-evaluator passed';
        evaluatorBadge.innerHTML = '<i class="fa-solid fa-circle-check"></i> PASSED (High Relevance)';
      } else {
        evaluatorBadge.className = 'badge-evaluator blocked';
        evaluatorBadge.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> HALLUCINATION BLOCKED';
      }
    }

    if (evaluatorReason && email.evaluator_reasoning) {
      evaluatorReason.textContent = email.evaluator_reasoning;
    }

    // Only allow SMTP send if evaluator passed
    if (sendEmailBtn) {
      sendEmailBtn.disabled = !passed;
    }

    showToast(passed ? 'Email generated & verified by Evaluator Agent!' : 'Evaluator blocked email due to score threshold.', !passed);

  } catch (err) {
    if (outputPlaceholder) outputPlaceholder.classList.add('d-none');
    showToast(err.message, true);
  } finally {
    setButtonLoading(btn, false);
  }
}

async function sendEmailSMTP(leadId) {
  const btn = document.getElementById('sendEmailBtn');
  const subject = document.getElementById('emailSubject').value.trim();
  const body = document.getElementById('emailBody').value.trim();

  if (!subject || !body) {
    showToast('Subject and Body cannot be empty.', true);
    return;
  }

  setButtonLoading(btn, true, 'Dispatching via SMTP...');
  try {
    const res = await fetch(`/api/leads/${leadId}/send-email`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subject, body })
    });
    const data = await res.json();
    if (!res.ok || !data.success) throw new Error(data.error || 'SMTP dispatch failed.');

    showModalAlert(
      'Email Dispatched!',
      `Personalized outreach was successfully sent to the lead via SMTP.`,
      'success'
    );

    // Update lead status badge if visible
    const statusBadge = document.getElementById('leadStatusBadge');
    if (statusBadge) {
      statusBadge.className = 'status-badge sent';
      statusBadge.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Sent';
    }
  } catch (err) {
    showToast(err.message, true);
  } finally {
    setButtonLoading(btn, false);
  }
}
