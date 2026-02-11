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

// Application state
let currentImage = null;
let currentBBox = null;
let detectedBBox = null;
let selectedFile = null;

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
