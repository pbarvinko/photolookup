/**
 * Main application entry point
 */

import { fetchBBox, lookupImage, saveDebug, fetchVersion } from './api.js';
import { render } from './canvas-renderer.js';
import { setupBBoxEditor, sanitizeBBox, handleMetrics } from './bbox-editor.js';
import { createSlider } from './slider.js';
import { loadImageWithOrientation } from './utils.js';

// DOM element references
const fileInput = document.getElementById('fileInput');
const browseBtn = document.getElementById('browseBtn');
const preview = document.getElementById('preview');
const previewCanvas = document.getElementById('previewCanvas');
const fileMeta = document.getElementById('fileMeta');
const ctx = previewCanvas.getContext('2d');
const lookupBtn = document.getElementById('lookupBtn');
const debugBtn = document.getElementById('debugBtn');
const results = document.getElementById('results');
const versionText = document.getElementById('versionText');

// Library modal references
const libraryLink = document.getElementById('libraryLink');
const libraryModal = document.getElementById('libraryModal');
const modalClose = document.getElementById('modalClose');
const modalCloseBtn = document.getElementById('modalCloseBtn');
const buildBtn = document.getElementById('buildBtn');
const libraryPaths = document.getElementById('libraryPaths');
const indexStatus = document.getElementById('indexStatus');
const indexDetails = document.getElementById('indexDetails');

// Application state
let currentImage = null;
let currentBBox = null;
let detectedBBox = null;
let selectedFile = null;

// Modal state
let modalOpen = false;
let modalRefreshInterval = null;
const MODAL_REFRESH_INTERVAL = 5000; // 5 seconds

// Initialize slider
const matchSlider = createSlider({
  resultsContainer: results,
  slider: document.querySelector('.slider'),
  sliderTrack: document.getElementById('sliderTrack'),
  slideStatus: document.getElementById('slideStatus'),
  sliderPrev: document.getElementById('sliderPrev'),
  sliderNext: document.getElementById('sliderNext'),
  previewCanvas,
});

// Render function wrapper
function renderCanvas() {
  const metrics = handleMetrics(previewCanvas);
  render(ctx, previewCanvas, currentImage, currentBBox, metrics);
}

// Initialize bbox editor
const cleanupBBoxEditor = setupBBoxEditor(previewCanvas, {
  getBBox: () => currentBBox,
  setBBox: (bbox) => { currentBBox = bbox; },
  onBBoxChange: renderCanvas,
});

// Browse button handler
browseBtn.addEventListener('click', () => {
  fileInput.click();
});

// File input change handler
fileInput.addEventListener('change', async () => {
  const file = fileInput.files && fileInput.files[0];
  if (!file) {
    preview.hidden = true;
    results.hidden = true;
    lookupBtn.disabled = true;
    debugBtn.hidden = true;
    return;
  }

  selectedFile = file;
  lookupBtn.disabled = false;
  debugBtn.hidden = false;
  results.hidden = true;
  matchSlider.reset();
  detectedBBox = null;

  const objectUrl = URL.createObjectURL(file);
  try {
    const imageData = await loadImageWithOrientation(file, objectUrl);
    currentImage = imageData.bitmap;
    previewCanvas.width = imageData.width;
    previewCanvas.height = imageData.height;
    currentBBox = null;
    renderCanvas();

    fileMeta.textContent = `${file.name} · ${(file.size / 1024).toFixed(1)} KB`;
    preview.hidden = false;

    try {
      const bbox = await fetchBBox(file);
      if (bbox) {
        detectedBBox = sanitizeBBox(bbox, previewCanvas.width, previewCanvas.height);
        currentBBox = detectedBBox.slice();
        renderCanvas();
      }
    } catch (err) {
      console.error('BBox request failed', err);
    }
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
});

// Lookup button handler
lookupBtn.addEventListener('click', async () => {
  if (!selectedFile) {
    return;
  }
  lookupBtn.disabled = true;
  try {
    const data = await lookupImage(selectedFile, currentBBox);
    matchSlider.renderMatches(data.matches || []);
  } catch (err) {
    console.error('Lookup failed', err);
  } finally {
    lookupBtn.disabled = false;
  }
});

// Debug button handler
debugBtn.addEventListener('click', async () => {
  if (!selectedFile) {
    return;
  }
  debugBtn.disabled = true;
  try {
    await saveDebug(selectedFile, detectedBBox, currentBBox);
  } catch (err) {
    console.error('Save debug failed', err);
  } finally {
    debugBtn.disabled = false;
  }
});

// Fetch and display version
(async () => {
  const version = await fetchVersion();
  if (version) {
    versionText.textContent = `PhotoLookup v${version}`;
  }
})();

// Library Modal Functions
async function openLibraryModal() {
  modalOpen = true;
  libraryModal.hidden = false;

  // Initial fetch
  await refreshLibraryInfo();

  // Start auto-refresh
  modalRefreshInterval = setInterval(refreshLibraryInfo, MODAL_REFRESH_INTERVAL);
}

function closeLibraryModal() {
  modalOpen = false;
  libraryModal.hidden = true;

  // Stop auto-refresh
  if (modalRefreshInterval) {
    clearInterval(modalRefreshInterval);
    modalRefreshInterval = null;
  }
}

async function refreshLibraryInfo() {
  try {
    // Fetch config and status in parallel
    const [configResp, statusResp] = await Promise.all([
      fetch('/api/config'),
      fetch('/api/index/status')
    ]);

    if (!configResp.ok || !statusResp.ok) {
      throw new Error('API request failed');
    }

    const config = await configResp.json();
    const status = await statusResp.json();

    renderLibraryInfo(config, status);
  } catch (err) {
    console.error('Failed to fetch library info:', err);
    indexStatus.textContent = 'Error loading data';
    indexStatus.className = 'status-badge status-error';
  }
}

function renderLibraryInfo(config, status) {
  // Render library paths
  libraryPaths.innerHTML = config.image_library_dirs
    .map(path => `<li>${escapeHtml(path)}</li>`)
    .join('');

  // Determine index state
  const buildStatus = status.build_status;
  const hasIndex = status.exists;

  if (buildStatus && buildStatus.status === 'running') {
    // Building state
    indexStatus.innerHTML = '<span class="spinner"></span> Building...';
    indexStatus.className = 'status-badge status-building';

    const progress = buildStatus.progress;
    const total = buildStatus.total;
    const progressText = total
      ? `${progress.toLocaleString()} / ${total.toLocaleString()} files`
      : `${progress.toLocaleString()} files`;

    const startTime = new Date(buildStatus.started_at).toLocaleString();

    indexDetails.innerHTML = `
      <div><strong>Progress:</strong> ${progressText}</div>
      <div><strong>Started:</strong> ${startTime}</div>
    `;

    buildBtn.disabled = true;
    buildBtn.textContent = 'Building...';

  } else if (buildStatus && buildStatus.status === 'failed') {
    // Error state
    indexStatus.textContent = '⚠ Error';
    indexStatus.className = 'status-badge status-error';

    const errorMsg = escapeHtml(buildStatus.error || 'Unknown error');
    indexDetails.innerHTML = `
      <div><strong>Error:</strong> ${errorMsg}</div>
      ${hasIndex ? `<div><strong>Last Index:</strong> ${status.count.toLocaleString()} files</div>` : ''}
    `;

    buildBtn.disabled = false;
    buildBtn.textContent = 'Build Index';

  } else if (hasIndex) {
    // Ready state
    indexStatus.textContent = '✓ Ready';
    indexStatus.className = 'status-badge status-ready';

    const lastUpdated = new Date(status.meta.updated_at).toLocaleString();
    const operation = status.meta.operation === 'build' ? 'Built' : 'Updated';

    indexDetails.innerHTML = `
      <div><strong>Total Files:</strong> ${status.count.toLocaleString()}</div>
      <div><strong>Last ${operation}:</strong> ${lastUpdated}</div>
    `;

    buildBtn.disabled = false;
    buildBtn.textContent = 'Build Index';

  } else {
    // No index state
    indexStatus.textContent = 'ℹ No Index';
    indexStatus.className = 'status-badge status-none';

    indexDetails.innerHTML = `
      <div>No index found. Build index to enable lookups.</div>
    `;

    buildBtn.disabled = false;
    buildBtn.textContent = 'Build Index';
  }
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Library Modal Event Handlers
libraryLink.addEventListener('click', (e) => {
  e.preventDefault();
  openLibraryModal();
});

modalClose.addEventListener('click', closeLibraryModal);
modalCloseBtn.addEventListener('click', closeLibraryModal);

libraryModal.querySelector('.modal-overlay').addEventListener('click', closeLibraryModal);

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && modalOpen) {
    closeLibraryModal();
  }
});

buildBtn.addEventListener('click', async () => {
  try {
    buildBtn.disabled = true;
    buildBtn.textContent = 'Starting...';

    const resp = await fetch('/api/index', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}'
    });

    if (resp.status === 409) {
      alert('Build already in progress');
    } else if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }

    // Immediately refresh to show building state
    await refreshLibraryInfo();
  } catch (err) {
    console.error('Build failed:', err);
    alert('Failed to start build. Check console for details.');
    buildBtn.disabled = false;
    buildBtn.textContent = 'Build Index';
  }
});
