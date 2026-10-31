"""
explore.py — ChromaDB Local Web Explorer
=========================================
A clean, zero-dependency web interface for browsing your local
ChromaDB vector database — all company collections, chunks,
metadata, and semantic search in one place.

Run:
    python explore.py

Then open:  http://localhost:7860

Features:
  - Dashboard: all collections with vector counts
  - Browse:    paginated chunk viewer with metadata
  - Search:    semantic query with scored results + highlights
  - Inspect:   single chunk detail view
  - Stats:     topic breakdown, source breakdown, strategy charts
"""

import os
import sys
import json
import math
import html
from datetime import datetime

# ── Ensure UTF-8 output on Windows console ────────────────────────
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, request, jsonify, render_template_string
import chromadb

from pipeline.config import CHROMA_DIR, CHROMA_COLLECTION_PREFIX
from pipeline.vector_store import VectorStore

# ─────────────────────────────────────────────────────────────────
PORT = 7860
app  = Flask(__name__)

# ─────────────────────────────────────────────────────────────────
# HTML Template (single-file SPA — no external files needed)
# ─────────────────────────────────────────────────────────────────

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ChromaDB Explorer — AI Sales Intelligence</title>
<style>
  :root {
    --bg: #0f1117; --surface: #1a1d27; --surface2: #22263a;
    --border: #2d3250; --accent: #6c63ff; --accent2: #48cae4;
    --green: #4caf87; --yellow: #f0c040; --red: #e05c5c;
    --text: #e2e8f0; --muted: #8892a4; --white: #ffffff;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; font-size: 14px; }

  /* Layout */
  .sidebar { position: fixed; top: 0; left: 0; width: 240px; height: 100vh;
             background: var(--surface); border-right: 1px solid var(--border);
             overflow-y: auto; z-index: 100; display: flex; flex-direction: column; }
  .main    { margin-left: 240px; min-height: 100vh; padding: 24px; }

  /* Sidebar */
  .sidebar-logo { padding: 20px 16px 12px; border-bottom: 1px solid var(--border); }
  .sidebar-logo h2 { font-size: 15px; font-weight: 700; color: var(--accent); }
  .sidebar-logo p  { font-size: 11px; color: var(--muted); margin-top: 2px; }
  .nav-section { padding: 12px 16px 4px; font-size: 10px; font-weight: 700;
                 text-transform: uppercase; letter-spacing: 1px; color: var(--muted); }
  .nav-item { display: flex; align-items: center; gap: 10px; padding: 9px 16px;
              cursor: pointer; color: var(--muted); transition: all 0.15s;
              border-left: 3px solid transparent; font-size: 13px; }
  .nav-item:hover, .nav-item.active {
    background: var(--surface2); color: var(--text); border-left-color: var(--accent); }
  .nav-item .icon { font-size: 16px; width: 20px; text-align: center; }
  .collection-pill { display: flex; justify-content: space-between; align-items: center;
                     padding: 7px 16px; cursor: pointer; border-left: 3px solid transparent;
                     transition: all 0.15s; color: var(--muted); font-size: 12px; }
  .collection-pill:hover { background: var(--surface2); color: var(--text); border-left-color: var(--accent2); }
  .collection-pill .count { background: var(--surface2); color: var(--accent2);
                             padding: 1px 6px; border-radius: 10px; font-size: 10px; }

  /* Top bar */
  .topbar { display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }
  .topbar h1 { font-size: 20px; font-weight: 700; }
  .topbar .badge { background: var(--accent); color: white; padding: 3px 10px;
                   border-radius: 12px; font-size: 11px; font-weight: 600; }
  .db-path { font-size: 11px; color: var(--muted); margin-top: 4px; }

  /* Cards */
  .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; margin-bottom: 28px; }
  .card  { background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
           padding: 20px; transition: border-color 0.2s; }
  .card:hover { border-color: var(--accent); }
  .card .label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
  .card .value { font-size: 28px; font-weight: 700; color: var(--accent); }
  .card .sub   { font-size: 11px; color: var(--muted); margin-top: 4px; }

  /* Table */
  .table-wrap { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; margin-bottom: 24px; }
  table { width: 100%; border-collapse: collapse; }
  th { background: var(--surface2); color: var(--muted); font-size: 11px; text-transform: uppercase;
       letter-spacing: 0.5px; padding: 10px 14px; text-align: left; }
  td { padding: 10px 14px; border-top: 1px solid var(--border); vertical-align: top; }
  tr:hover td { background: var(--surface2); }
  .chunk-text { max-width: 420px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
                color: var(--muted); font-size: 12px; }
  .tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 10px;
         font-weight: 600; margin-right: 3px; margin-bottom: 2px; }
  .tag-source    { background: #1e3a5f; color: var(--accent2); }
  .tag-strategy  { background: #2d1e5f; color: #b39ddb; }
  .tag-topic     { background: #1e4a2d; color: var(--green); }
  .tag-page      { background: #3a2d1e; color: var(--yellow); }

  /* Search */
  .search-box { display: flex; gap: 10px; margin-bottom: 20px; }
  .search-input { flex: 1; background: var(--surface); border: 1px solid var(--border);
                  border-radius: 8px; padding: 10px 14px; color: var(--text); font-size: 14px; outline: none; }
  .search-input:focus { border-color: var(--accent); }
  .btn { background: var(--accent); color: white; border: none; border-radius: 8px;
         padding: 10px 20px; cursor: pointer; font-size: 13px; font-weight: 600;
         transition: opacity 0.15s; white-space: nowrap; }
  .btn:hover { opacity: 0.85; }
  .btn-outline { background: transparent; border: 1px solid var(--border); color: var(--text); }
  .btn-outline:hover { border-color: var(--accent); color: var(--accent); opacity: 1; }
  .btn-sm { padding: 5px 12px; font-size: 11px; }
  .collection-select { background: var(--surface); border: 1px solid var(--border);
                        border-radius: 8px; padding: 10px 12px; color: var(--text); font-size: 13px; }

  /* Result cards */
  .result-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
                 padding: 16px; margin-bottom: 14px; transition: border-color 0.2s; }
  .result-card:hover { border-color: var(--accent); }
  .result-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px; }
  .score-badge { font-size: 18px; font-weight: 700; }
  .score-high  { color: var(--green); }
  .score-mid   { color: var(--yellow); }
  .score-low   { color: var(--red); }
  .result-text { color: var(--muted); font-size: 13px; line-height: 1.6; }
  mark { background: rgba(108, 99, 255, 0.25); color: var(--text); border-radius: 2px; padding: 0 2px; }

  /* Pagination */
  .pagination { display: flex; gap: 6px; justify-content: center; margin-top: 16px; }
  .page-btn { padding: 6px 12px; border-radius: 6px; border: 1px solid var(--border);
              background: var(--surface); color: var(--muted); cursor: pointer; font-size: 12px; }
  .page-btn:hover { border-color: var(--accent); color: var(--accent); }
  .page-btn.active { background: var(--accent); color: white; border-color: var(--accent); }

  /* Stats bars */
  .stat-row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
  .stat-label { width: 180px; font-size: 12px; color: var(--muted); text-align: right; flex-shrink: 0; }
  .stat-bar-wrap { flex: 1; background: var(--surface2); border-radius: 4px; height: 10px; overflow: hidden; }
  .stat-bar { height: 100%; border-radius: 4px; background: var(--accent); transition: width 0.5s; }
  .stat-count { width: 50px; font-size: 11px; color: var(--accent); font-weight: 700; }

  /* Panel switching */
  .panel { display: none; }
  .panel.active { display: block; }

  /* Detail modal */
  .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.7); z-index: 200;
                   display: none; align-items: center; justify-content: center; }
  .modal-overlay.open { display: flex; }
  .modal { background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
           padding: 24px; max-width: 700px; width: 95%; max-height: 80vh; overflow-y: auto; }
  .modal-title { font-size: 16px; font-weight: 700; margin-bottom: 16px; color: var(--accent); }
  .meta-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 14px; }
  .meta-item { background: var(--surface2); padding: 8px 12px; border-radius: 6px; }
  .meta-item .key { font-size: 10px; color: var(--muted); text-transform: uppercase; }
  .meta-item .val { font-size: 13px; font-weight: 600; margin-top: 2px; }
  .full-text { background: var(--surface2); padding: 14px; border-radius: 8px; font-size: 12px;
               line-height: 1.7; color: var(--muted); white-space: pre-wrap; max-height: 300px; overflow-y: auto; }
  .close-btn { float: right; cursor: pointer; color: var(--muted); font-size: 20px; }
  .close-btn:hover { color: var(--text); }

  /* Alerts */
  .alert { padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; font-size: 13px; }
  .alert-info { background: #1a2a4a; border: 1px solid #2d4a7a; color: var(--accent2); }
  .alert-warn { background: #3a2d1e; border: 1px solid #7a5a1e; color: var(--yellow); }
  .empty { text-align: center; padding: 60px 20px; color: var(--muted); }
  .empty .icon { font-size: 48px; margin-bottom: 12px; }
  .spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid var(--border);
             border-top-color: var(--accent); border-radius: 50%; animation: spin 0.7s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .flex { display: flex; } .gap-8 { gap: 8px; } .items-center { align-items: center; }
  .mt-16 { margin-top: 16px; } .mb-8 { margin-bottom: 8px; }
  code { background: var(--surface2); padding: 1px 6px; border-radius: 4px; font-family: monospace; font-size: 12px; }
</style>
</head>
<body>

<!-- Sidebar -->
<aside class="sidebar">
  <div class="sidebar-logo">
    <h2>&#x1F9E0; ChromaDB Explorer</h2>
    <p>AI Sales Intelligence</p>
  </div>

  <div class="nav-section">Navigation</div>
  <div class="nav-item active" onclick="showPanel('dashboard')">
    <span class="icon">&#x1F4CA;</span> Dashboard
  </div>
  <div class="nav-item" onclick="showPanel('browse')">
    <span class="icon">&#x1F4C4;</span> Browse Chunks
  </div>
  <div class="nav-item" onclick="showPanel('search')">
    <span class="icon">&#x1F50D;</span> Semantic Search
  </div>
  <div class="nav-item" onclick="showPanel('stats')">
    <span class="icon">&#x1F4C8;</span> Statistics
  </div>

  <div class="nav-section" style="margin-top:12px">Collections</div>
  <div id="sidebar-collections">
    <div style="padding:12px 16px; color:var(--muted); font-size:12px;">Loading...</div>
  </div>
</aside>

<!-- Main Content -->
<main class="main">

  <!-- DASHBOARD -->
  <div id="panel-dashboard" class="panel active">
    <div class="topbar">
      <div>
        <h1>&#x1F4CA; Dashboard</h1>
        <div class="db-path" id="db-path-display">Loading database...</div>
      </div>
      <div class="badge" id="live-badge">LIVE</div>
    </div>
    <div class="cards" id="dashboard-cards">
      <div class="card"><div class="label">Total Collections</div><div class="value" id="stat-cols">—</div><div class="sub">companies indexed</div></div>
      <div class="card"><div class="label">Total Vectors</div><div class="value" id="stat-vecs">—</div><div class="sub">embedded chunks</div></div>
      <div class="card"><div class="label">Embedding Model</div><div class="value" style="font-size:16px;margin-top:6px" id="stat-emb">—</div><div class="sub" id="stat-dims">dimensions</div></div>
      <div class="card"><div class="label">Storage Path</div><div class="value" style="font-size:11px;margin-top:6px;word-break:break-all" id="stat-path">—</div></div>
    </div>

    <h3 style="margin-bottom:14px; font-size:15px;">Collections</h3>
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th>Collection</th><th>Company</th><th>Vectors</th>
          <th>Embedding</th><th>Dimensions</th><th>Actions</th>
        </tr></thead>
        <tbody id="collections-table">
          <tr><td colspan="6" style="text-align:center;color:var(--muted);padding:30px">Loading...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- BROWSE -->
  <div id="panel-browse" class="panel">
    <div class="topbar">
      <h1>&#x1F4C4; Browse Chunks</h1>
    </div>
    <div class="flex gap-8 mb-8" style="flex-wrap:wrap">
      <select class="collection-select" id="browse-collection" onchange="loadBrowse(1)">
        <option value="">Select collection...</option>
      </select>
      <select class="collection-select" id="browse-source" onchange="loadBrowse(1)">
        <option value="">All sources</option>
      </select>
      <select class="collection-select" id="browse-strategy" onchange="loadBrowse(1)">
        <option value="">All strategies</option>
      </select>
      <input class="search-input" style="max-width:200px" id="browse-topic" placeholder="Filter by topic..." oninput="loadBrowse(1)">
    </div>
    <div id="browse-content">
      <div class="empty"><div class="icon">&#x1F4C2;</div><p>Select a collection to browse chunks</p></div>
    </div>
    <div class="pagination" id="browse-pagination"></div>
  </div>

  <!-- SEARCH -->
  <div id="panel-search" class="panel">
    <div class="topbar">
      <h1>&#x1F50D; Semantic Search</h1>
    </div>
    <div class="alert alert-info">
      Semantic search finds chunks by <strong>meaning</strong>, not just keywords.
      Results are ranked by cosine similarity score (0–100%).
    </div>
    <div class="flex gap-8 mb-8" style="flex-wrap:wrap;margin-bottom:16px">
      <select class="collection-select" id="search-collection">
        <option value="">All collections</option>
      </select>
      <input class="search-input" id="search-k" type="number" value="5" min="1" max="20" style="max-width:100px" placeholder="Top K">
    </div>
    <div class="search-box">
      <input class="search-input" id="search-query" placeholder="e.g. What is the company's annual revenue?" onkeydown="if(event.key==='Enter')runSearch()">
      <button class="btn" onclick="runSearch()">&#x1F50D; Search</button>
    </div>

    <div style="margin-bottom:16px">
      <span style="font-size:12px;color:var(--muted);">Try: </span>
      <span class="tag tag-topic" style="cursor:pointer" onclick="setQuery(this)">revenue and funding</span>
      <span class="tag tag-topic" style="cursor:pointer" onclick="setQuery(this)">CEO and leadership team</span>
      <span class="tag tag-topic" style="cursor:pointer" onclick="setQuery(this)">products and services offered</span>
      <span class="tag tag-topic" style="cursor:pointer" onclick="setQuery(this)">number of employees</span>
      <span class="tag tag-topic" style="cursor:pointer" onclick="setQuery(this)">competitors and market</span>
    </div>

    <div id="search-results">
      <div class="empty"><div class="icon">&#x1F50D;</div><p>Enter a query above to search</p></div>
    </div>
  </div>

  <!-- STATS -->
  <div id="panel-stats" class="panel">
    <div class="topbar">
      <h1>&#x1F4C8; Statistics</h1>
    </div>
    <div class="flex gap-8 mb-8">
      <select class="collection-select" id="stats-collection" onchange="loadStats()">
        <option value="">Select collection...</option>
      </select>
    </div>
    <div id="stats-content">
      <div class="empty"><div class="icon">&#x1F4C8;</div><p>Select a collection to view statistics</p></div>
    </div>
  </div>

</main>

<!-- Detail Modal -->
<div class="modal-overlay" id="modal-overlay" onclick="closeModal(event)">
  <div class="modal" id="modal-content">
    <span class="close-btn" onclick="closeModal()">&#x2715;</span>
    <div id="modal-body"></div>
  </div>
</div>

<script>
// ── State ──────────────────────────────────────────────────────────
let collections = [];
let browseState = { page: 1, perPage: 20, total: 0, col: '' };

// ── Panel switcher ─────────────────────────────────────────────────
function showPanel(name) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('panel-' + name).classList.add('active');
  document.querySelector('[onclick="showPanel(\'' + name + '\')"]').classList.add('active');
  if (name === 'browse' && !document.getElementById('browse-collection').value) loadCollectionSelects();
  if (name === 'search') loadCollectionSelects();
  if (name === 'stats') loadCollectionSelects();
}

// ── API helpers ────────────────────────────────────────────────────
async function api(url, method='GET', body=null) {
  const opts = { method, headers: {'Content-Type':'application/json'} };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(url, opts);
  return r.json();
}

// ── Dashboard ──────────────────────────────────────────────────────
async function loadDashboard() {
  const data = await api('/api/collections');
  collections = data.collections || [];
  document.getElementById('stat-cols').textContent = collections.length;
  const totalVecs = collections.reduce((s, c) => s + c.count, 0);
  document.getElementById('stat-vecs').textContent = totalVecs.toLocaleString();
  document.getElementById('stat-emb').textContent = data.embedder || '—';
  document.getElementById('stat-dims').textContent = (data.dimensions || '—') + ' dimensions';
  document.getElementById('stat-path').textContent = data.path || '—';
  document.getElementById('db-path-display').textContent = 'DB: ' + (data.path || '—');

  // Collections table
  const tbody = document.getElementById('collections-table');
  if (!collections.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty"><div class="icon">&#x1F4ED;</div><p>No collections yet. Run the pipeline first:<br><code>python run_pipeline.py --company "Tesla"</code></p></td></tr>';
    return;
  }
  tbody.innerHTML = collections.map(c => `
    <tr>
      <td><code>${c.name}</code></td>
      <td><strong>${c.company || '—'}</strong></td>
      <td><span class="tag tag-source">${c.count.toLocaleString()} vectors</span></td>
      <td>${c.embedding || '—'}</td>
      <td>${c.dims || '—'}</td>
      <td>
        <button class="btn btn-sm btn-outline" onclick="goToBrowse('${c.name}')">Browse</button>
        <button class="btn btn-sm btn-outline" onclick="goToSearch('${c.name}')" style="margin-left:4px">Search</button>
        <button class="btn btn-sm btn-outline" onclick="goToStats('${c.name}')" style="margin-left:4px">Stats</button>
      </td>
    </tr>`).join('');

  // Sidebar
  const sidebar = document.getElementById('sidebar-collections');
  sidebar.innerHTML = collections.map(c => `
    <div class="collection-pill" onclick="goToBrowse('${c.name}')">
      <span>${c.company || c.name}</span>
      <span class="count">${c.count}</span>
    </div>`).join('') || '<div style="padding:12px 16px;color:var(--muted);font-size:12px">No collections</div>';
}

function goToBrowse(col) {
  showPanel('browse');
  document.getElementById('browse-collection').value = col;
  loadBrowse(1);
}
function goToSearch(col) {
  showPanel('search');
  document.getElementById('search-collection').value = col;
}
function goToStats(col) {
  showPanel('stats');
  document.getElementById('stats-collection').value = col;
  loadStats();
}

// ── Browse ─────────────────────────────────────────────────────────
async function loadCollectionSelects() {
  if (!collections.length) {
    const data = await api('/api/collections');
    collections = data.collections || [];
  }
  ['browse-collection','search-collection','stats-collection'].forEach(id => {
    const sel = document.getElementById(id);
    if (!sel) return;
    const current = sel.value;
    const opts = collections.map(c => `<option value="${c.name}">${c.company || c.name} (${c.count})</option>`).join('');
    sel.innerHTML = (id === 'browse-collection' ? '' : '<option value="">All collections</option>') + opts;
    if (current) sel.value = current;
  });
}

async function loadBrowse(page) {
  const col = document.getElementById('browse-collection').value;
  if (!col) return;
  browseState.col  = col;
  browseState.page = page || 1;
  const source   = document.getElementById('browse-source').value;
  const strategy = document.getElementById('browse-strategy').value;
  const topic    = document.getElementById('browse-topic').value;

  const data = await api(`/api/chunks?collection=${col}&page=${browseState.page}&per_page=${browseState.perPage}&source=${source}&strategy=${strategy}&topic=${encodeURIComponent(topic)}`);
  browseState.total = data.total || 0;

  if (data.sources) {
    const src = document.getElementById('browse-source');
    const cur = src.value;
    src.innerHTML = '<option value="">All sources</option>' + data.sources.map(s => `<option value="${s}">${s}</option>`).join('');
    if (cur) src.value = cur;
  }
  if (data.strategies) {
    const st = document.getElementById('browse-strategy');
    const cur = st.value;
    st.innerHTML = '<option value="">All strategies</option>' + data.strategies.map(s => `<option value="${s}">${s}</option>`).join('');
    if (cur) st.value = cur;
  }

  const chunks = data.chunks || [];
  const cont = document.getElementById('browse-content');
  if (!chunks.length) {
    cont.innerHTML = '<div class="empty"><div class="icon">&#x1F4ED;</div><p>No chunks found</p></div>';
    document.getElementById('browse-pagination').innerHTML = '';
    return;
  }

  cont.innerHTML = `
    <div style="color:var(--muted);font-size:12px;margin-bottom:10px">
      Showing ${(browseState.page-1)*browseState.perPage + 1}–${Math.min(browseState.page*browseState.perPage, browseState.total)} of ${browseState.total.toLocaleString()} chunks
    </div>
    <div class="table-wrap">
    <table>
      <thead><tr>
        <th>#</th><th>Text Preview</th><th>Source</th><th>Strategy</th>
        <th>Page</th><th>Tokens</th><th>Topics</th><th></th>
      </tr></thead>
      <tbody>` +
    chunks.map((c, i) => `<tr>
      <td style="color:var(--muted)">${(browseState.page-1)*browseState.perPage + i + 1}</td>
      <td><div class="chunk-text" title="${escHtml(c.text)}">${escHtml(c.text.substring(0,100))}...</div></td>
      <td><span class="tag tag-source">${c.source||'—'}</span></td>
      <td><span class="tag tag-strategy">${c.strategy||'—'}</span></td>
      <td>${c.page_number > 0 ? '<span class="tag tag-page">p.'+c.page_number+'</span>' : '—'}</td>
      <td style="color:var(--accent)">${c.token_count||'—'}</td>
      <td>${(c.topics||'').split(',').filter(t=>t.trim()).map(t=>'<span class="tag tag-topic">'+t.trim()+'</span>').join('')}</td>
      <td><button class="btn btn-sm btn-outline" onclick='showChunkDetail(${JSON.stringify(c).replace(/'/g,"&#39;")})'>View</button></td>
    </tr>`).join('') +
    '</tbody></table></div>';

  renderPagination(browseState.total, browseState.page, browseState.perPage);
}

function renderPagination(total, current, perPage) {
  const pages = Math.ceil(total / perPage);
  const el = document.getElementById('browse-pagination');
  if (pages <= 1) { el.innerHTML = ''; return; }
  let html = '';
  for (let p = Math.max(1, current-3); p <= Math.min(pages, current+3); p++) {
    html += `<span class="page-btn ${p===current?'active':''}" onclick="loadBrowse(${p})">${p}</span>`;
  }
  el.innerHTML = `<span class="page-btn" onclick="loadBrowse(${Math.max(1,current-1)})">&#x2190;</span>` +
    html + `<span class="page-btn" onclick="loadBrowse(${Math.min(pages,current+1)})">&#x2192;</span>`;
}

// ── Search ─────────────────────────────────────────────────────────
function setQuery(el) {
  document.getElementById('search-query').value = el.textContent;
  runSearch();
}

async function runSearch() {
  const query = document.getElementById('search-query').value.trim();
  if (!query) return;
  const col = document.getElementById('search-collection').value;
  const k   = parseInt(document.getElementById('search-k').value) || 5;
  const el  = document.getElementById('search-results');
  el.innerHTML = '<div style="padding:30px;text-align:center"><div class="spinner"></div> Searching...</div>';

  const data = await api('/api/search', 'POST', { query, collection: col, top_k: k });
  const results = data.results || [];

  if (!results.length) {
    el.innerHTML = '<div class="alert alert-warn">No results found. Try a different query or add more data.</div>';
    return;
  }

  el.innerHTML = `<div style="color:var(--muted);font-size:12px;margin-bottom:12px">${results.length} results for: <strong style="color:var(--text)">"${escHtml(query)}"</strong></div>` +
    results.map((r, i) => {
      const sc = r.score;
      const cls = sc >= 70 ? 'score-high' : sc >= 40 ? 'score-mid' : 'score-low';
      const highlighted = highlightQuery(r.text, query);
      return `<div class="result-card">
        <div class="result-header">
          <div>
            <span class="tag tag-source">${r.source||'—'}</span>
            ${r.page_number>0 ? '<span class="tag tag-page">Page '+r.page_number+'</span>' : ''}
            <span class="tag tag-strategy">${r.strategy||'—'}</span>
            <div style="margin-top:6px;font-size:12px;color:var(--muted)">${escHtml(r.title||'').substring(0,80)}</div>
          </div>
          <div class="score-badge ${cls}">${sc.toFixed(1)}%</div>
        </div>
        <div class="result-text">${highlighted}</div>
        <div style="margin-top:10px">
          ${(r.topics||'').split(',').filter(t=>t.trim()).map(t=>'<span class="tag tag-topic">'+t.trim()+'</span>').join('')}
          <button class="btn btn-sm btn-outline" style="margin-left:8px" onclick='showChunkDetail(${JSON.stringify(r).replace(/'/g,"&#39;")})'>Full text</button>
        </div>
      </div>`;
    }).join('');
}

function highlightQuery(text, query) {
  const safe = escHtml(text.substring(0, 500));
  const words = query.split(' ').filter(w => w.length > 3).map(w => escHtml(w));
  let result = safe;
  words.forEach(w => {
    result = result.replace(new RegExp(w, 'gi'), m => '<mark>' + m + '</mark>');
  });
  return result + (text.length > 500 ? '...' : '');
}

// ── Stats ──────────────────────────────────────────────────────────
async function loadStats() {
  const col = document.getElementById('stats-collection').value;
  if (!col) return;
  const el = document.getElementById('stats-content');
  el.innerHTML = '<div style="padding:30px;text-align:center"><div class="spinner"></div> Loading...</div>';
  const data = await api('/api/stats?collection=' + col);
  const s = data.stats || {};

  const renderBars = (obj, title, maxVal) => {
    if (!obj || !Object.keys(obj).length) return '';
    const max = maxVal || Math.max(...Object.values(obj));
    return `<div class="card" style="margin-bottom:16px">
      <div class="label">${title}</div>
      <div style="margin-top:12px">` +
      Object.entries(obj).sort((a,b)=>b[1]-a[1]).map(([k,v]) =>
        `<div class="stat-row">
          <div class="stat-label">${escHtml(k)}</div>
          <div class="stat-bar-wrap"><div class="stat-bar" style="width:${Math.round(v/max*100)}%"></div></div>
          <div class="stat-count">${v}</div>
        </div>`).join('') + '</div></div>';
  };

  el.innerHTML = `
    <div class="cards">
      <div class="card"><div class="label">Total Chunks</div><div class="value">${(s.total||0).toLocaleString()}</div></div>
      <div class="card"><div class="label">Unique Pages</div><div class="value">${s.unique_pages||0}</div></div>
      <div class="card"><div class="label">Avg Tokens/Chunk</div><div class="value">${s.avg_tokens||0}</div></div>
      <div class="card"><div class="label">Total Words</div><div class="value">${(s.total_words||0).toLocaleString()}</div></div>
    </div>
    ${renderBars(s.by_source,   'Chunks by Source')}
    ${renderBars(s.by_strategy, 'Chunks by Chunking Strategy')}
    ${renderBars(s.by_topic,    'Chunks by Topic')}
  `;
}

// ── Chunk detail modal ──────────────────────────────────────────────
function showChunkDetail(chunk) {
  const body = document.getElementById('modal-body');
  body.innerHTML = `
    <div class="modal-title">&#x1F4C4; Chunk Detail</div>
    <div class="meta-grid">
      <div class="meta-item"><div class="key">Source</div><div class="val">${chunk.source||'—'}</div></div>
      <div class="meta-item"><div class="key">Strategy</div><div class="val">${chunk.strategy||'—'}</div></div>
      <div class="meta-item"><div class="key">Page Number</div><div class="val">${chunk.page_number||'—'}</div></div>
      <div class="meta-item"><div class="key">Token Count</div><div class="val">${chunk.token_count||'—'}</div></div>
      <div class="meta-item"><div class="key">Chunk Index</div><div class="val">${chunk.chunk_index||0} / ${chunk.total_chunks||1}</div></div>
      <div class="meta-item"><div class="key">Score</div><div class="val">${chunk.score ? chunk.score.toFixed(1)+'%' : '—'}</div></div>
    </div>
    <div class="mb-8"><strong style="font-size:12px">Title:</strong> <code>${escHtml((chunk.title||'').substring(0,100))}</code></div>
    <div class="mb-8"><strong style="font-size:12px">Topics:</strong> ${(chunk.topics||'').split(',').filter(t=>t.trim()).map(t=>'<span class="tag tag-topic">'+t.trim()+'</span>').join('') || '—'}</div>
    <div class="mb-8" style="margin-top:12px"><strong style="font-size:12px">Full Text:</strong></div>
    <div class="full-text">${escHtml(chunk.text||'')}</div>
  `;
  document.getElementById('modal-overlay').classList.add('open');
}

function closeModal(e) {
  if (!e || e.target === document.getElementById('modal-overlay')) {
    document.getElementById('modal-overlay').classList.remove('open');
  }
}

// ── Helpers ────────────────────────────────────────────────────────
function escHtml(str) {
  return String(str||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Init ───────────────────────────────────────────────────────────
loadDashboard();
</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────
# Chroma helpers
# ─────────────────────────────────────────────────────────────────

def _get_client():
    return chromadb.PersistentClient(path=CHROMA_DIR)


def _list_collections():
    client = _get_client()
    cols = []
    for c in client.list_collections():
        meta = c.metadata or {}
        cols.append({
            "name":      c.name,
            "company":   meta.get("company", c.name.replace(CHROMA_COLLECTION_PREFIX + "_", "").replace("_", " ").title()),
            "count":     c.count(),
            "embedding": meta.get("embedding", "—"),
            "dims":      meta.get("dims", "—"),
        })
    return cols


# ─────────────────────────────────────────────────────────────────
# API Routes
# ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/collections")
def api_collections():
    try:
        cols = _list_collections()
        total_vecs = sum(c["count"] for c in cols)
        embedder = cols[0]["embedding"] if cols else "—"
        dims     = cols[0]["dims"] if cols else "—"
        return jsonify({
            "collections": cols,
            "total_vectors": total_vecs,
            "embedder": embedder,
            "dimensions": dims,
            "path": CHROMA_DIR,
        })
    except Exception as e:
        return jsonify({"error": str(e), "collections": []}), 200


@app.route("/api/chunks")
def api_chunks():
    col_name  = request.args.get("collection", "")
    page      = int(request.args.get("page", 1))
    per_page  = int(request.args.get("per_page", 20))
    src_filt  = request.args.get("source", "")
    strat_filt= request.args.get("strategy", "")
    topic_filt= request.args.get("topic", "").strip().lower()

    if not col_name:
        return jsonify({"error": "collection required"}), 400

    try:
        client = _get_client()
        col = client.get_collection(col_name)

        # Fetch all with metadata (ChromaDB doesn't support complex filter on free-text)
        total_count = col.count()
        # Fetch up to 2000 for filtering (reasonable limit)
        limit = min(total_count, 2000)
        raw = col.get(
            limit=limit,
            include=["documents", "metadatas"],
        )

        # Build flat list
        items = []
        all_sources, all_strategies = set(), set()
        for doc, meta in zip(raw["documents"], raw["metadatas"]):
            m = meta or {}
            all_sources.add(m.get("source", ""))
            all_strategies.add(m.get("strategy", ""))

            # Apply filters
            if src_filt and m.get("source") != src_filt:
                continue
            if strat_filt and m.get("strategy") != strat_filt:
                continue
            if topic_filt and topic_filt not in (m.get("topics", "") or "").lower():
                continue

            items.append({
                "text":         doc,
                "source":       m.get("source", ""),
                "title":        m.get("title", ""),
                "url":          m.get("url", ""),
                "page_number":  m.get("page_number", 0),
                "chunk_index":  m.get("chunk_index", 0),
                "total_chunks": m.get("total_chunks", 1),
                "strategy":     m.get("strategy", ""),
                "token_count":  m.get("token_count", 0),
                "topics":       m.get("topics", ""),
                "processed_at": m.get("processed_at", ""),
            })

        # Paginate
        total = len(items)
        start = (page - 1) * per_page
        end   = start + per_page
        page_items = items[start:end]

        return jsonify({
            "chunks":     page_items,
            "total":      total,
            "page":       page,
            "per_page":   per_page,
            "sources":    sorted(s for s in all_sources if s),
            "strategies": sorted(s for s in all_strategies if s),
        })

    except Exception as e:
        return jsonify({"error": str(e), "chunks": [], "total": 0}), 200


@app.route("/api/search", methods=["POST"])
def api_search():
    body      = request.get_json() or {}
    query     = body.get("query", "").strip()
    col_name  = body.get("collection", "")
    top_k     = int(body.get("top_k", 5))

    if not query:
        return jsonify({"error": "query required"}), 400

    results = []
    try:
        # Determine which collections to search
        if col_name:
            col_names = [col_name]
        else:
            cols = _list_collections()
            col_names = [c["name"] for c in cols]

        for cn in col_names:
            company = cn.replace(CHROMA_COLLECTION_PREFIX + "_", "").replace("_", " ").title()
            vs = VectorStore(company)
            vs._collection = vs._client.get_collection(cn)
            res = vs.query(query, top_k=top_k)
            results.extend(res)

        # Sort all results by score, take top_k
        results.sort(key=lambda x: x["score"], reverse=True)
        results = results[:top_k]

    except Exception as e:
        return jsonify({"error": str(e), "results": []}), 200

    return jsonify({"results": results, "query": query})


@app.route("/api/stats")
def api_stats():
    col_name = request.args.get("collection", "")
    if not col_name:
        return jsonify({"error": "collection required"}), 400

    try:
        client = _get_client()
        col    = client.get_collection(col_name)
        total  = col.count()

        raw = col.get(limit=min(total, 5000), include=["metadatas"])
        metas = raw["metadatas"] or []

        by_source   = {}
        by_strategy = {}
        by_topic    = {}
        token_sum   = 0
        word_sum    = 0
        pages       = set()

        for m in metas:
            m = m or {}
            src = m.get("source", "unknown")
            st  = m.get("strategy", "unknown")
            tok = int(m.get("token_count", 0))
            wds = int(m.get("word_count", 0))
            pg  = m.get("page_number", 0)

            by_source[src]   = by_source.get(src, 0) + 1
            by_strategy[st]  = by_strategy.get(st, 0) + 1
            token_sum += tok
            word_sum  += wds
            if pg:
                pages.add(pg)

            for topic in (m.get("topics") or "").split(","):
                t = topic.strip()
                if t:
                    by_topic[t] = by_topic.get(t, 0) + 1

        return jsonify({
            "stats": {
                "total":        total,
                "unique_pages": len(pages),
                "avg_tokens":   round(token_sum / max(total, 1)),
                "total_words":  word_sum,
                "by_source":    by_source,
                "by_strategy":  by_strategy,
                "by_topic":     by_topic,
            }
        })

    except Exception as e:
        return jsonify({"error": str(e), "stats": {}}), 200


# ─────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print()
    print("=" * 62)
    print("  ChromaDB Explorer — AI Sales Intelligence")
    print("=" * 62)
    print(f"  DB path   : {CHROMA_DIR}")

    # Show available collections
    try:
        cols = _list_collections()
        print(f"  Collections: {len(cols)}")
        for c in cols:
            print(f"    - {c['name']}  ({c['count']} vectors)")
    except Exception as e:
        print(f"  [WARN] Could not read DB: {e}")

    print()
    print(f"  Open in browser: http://localhost:{PORT}")
    print(f"  Press Ctrl+C to stop")
    print("=" * 62)
    print()

    app.run(host="0.0.0.0", port=PORT, debug=False)
