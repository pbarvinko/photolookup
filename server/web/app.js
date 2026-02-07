const fileInput = document.getElementById('fileInput');
const browseBtn = document.getElementById('browseBtn');
const preview = document.getElementById('preview');
const previewCanvas = document.getElementById('previewCanvas');
const fileMeta = document.getElementById('fileMeta');
const ctx = previewCanvas.getContext('2d');
const lookupBtn = document.getElementById('lookupBtn');
const debugBtn = document.getElementById('debugBtn');
const results = document.getElementById('results');
const slider = document.querySelector('.slider');
const sliderTrack = document.getElementById('sliderTrack');
const slideStatus = document.getElementById('slideStatus');

let currentImage = null;
let currentBBox = null;
let detectedBBox = null;
let activeHandle = null;
let isDragging = false;
let lastPointer = null;
let grabOffset = null;
let selectedFile = null;
let matches = [];
let activeIndex = 0;
let swipeStart = null;

browseBtn.addEventListener('click', () => {
  fileInput.click();
});

fileInput.addEventListener('change', () => {
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
  sliderTrack.innerHTML = '';
  matches = [];
  activeIndex = 0;
  updateSlider();
  detectedBBox = null;

  const objectUrl = URL.createObjectURL(file);
  (async () => {
    const imageData = await loadImageWithOrientation(file, objectUrl);
    currentImage = imageData.bitmap;
    previewCanvas.width = imageData.width;
    previewCanvas.height = imageData.height;
    currentBBox = null;
    render();

    fileMeta.textContent = `${file.name} · ${(file.size / 1024).toFixed(1)} KB`;
    preview.hidden = false;

    try {
      const bbox = await fetchBBox(file);
      if (bbox) {
        detectedBBox = sanitizeBBox(bbox);
        currentBBox = detectedBBox.slice();
        render();
      }
    } catch (err) {
      console.error('BBox request failed', err);
    }

    URL.revokeObjectURL(objectUrl);
  })();
});

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

lookupBtn.addEventListener('click', async () => {
  if (!selectedFile) {
    return;
  }
  lookupBtn.disabled = true;
  try {
    const data = await lookupImage(selectedFile, currentBBox);
    matches = data.matches || [];
    activeIndex = 0;
    renderMatches();
  } catch (err) {
    console.error('Lookup failed', err);
  } finally {
    lookupBtn.disabled = false;
  }
});

async function fetchBBox(file) {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch('/api/bbox', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    return null;
  }
  const data = await response.json();
  return data.bbox;
}

function drawBBox(bbox) {
  const [x0, y0, x1, y1] = bbox;
  const width = x1 - x0 + 1;
  const height = y1 - y0 + 1;

  ctx.lineJoin = 'round';

  const base = Math.min(previewCanvas.width, previewCanvas.height);
  const outer = Math.max(10, base * 0.01);
  const inner = Math.max(4, base * 0.005);

  // Outer stroke for contrast
  ctx.strokeStyle = 'white';
  ctx.lineWidth = outer;
  ctx.strokeRect(x0, y0, width, height);

  // Inner stroke for visibility on light areas
  ctx.strokeStyle = 'black';
  ctx.lineWidth = inner;
  ctx.strokeRect(x0, y0, width, height);

  drawHandles(x0, y0, x1, y1);
}

async function lookupImage(file, bbox) {
  const formData = new FormData();
  formData.append('file', file);
  const url = new URL('/api/lookup', window.location.origin);
  if (bbox) {
    const ints = bbox.map((value) => Math.round(value));
    url.searchParams.set('bbox', ints.join(','));
  }
  const response = await fetch(url.toString(), {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    throw new Error(`Lookup failed: ${response.status}`);
  }
  return response.json();
}

async function saveDebug(file, detected, bbox) {
  const formData = new FormData();
  formData.append('file', file);
  if (detected) {
    const ints = detected.map((value) => Math.round(value));
    formData.append('detected_bbox', ints.join(','));
  }
  if (bbox) {
    const ints = bbox.map((value) => Math.round(value));
    formData.append('bbox', ints.join(','));
  }
  const response = await fetch('/api/debug', {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    throw new Error(`Debug save failed: ${response.status}`);
  }
  return response.json();
}

function renderMatches() {
  if (!matches.length) {
    results.hidden = true;
    return;
  }
  sliderTrack.innerHTML = '';
  const displayWidth = previewCanvas.getBoundingClientRect().width;
  if (slider) {
    slider.style.width = `${displayWidth}px`;
  }
  matches.slice(0, 3).forEach((match) => {
    const slide = document.createElement('div');
    slide.className = 'slide';

    const img = document.createElement('img');
    img.src = `/api/image?id=${encodeURIComponent(match.id)}`;
    img.alt = 'Matched image';

    const info = document.createElement('div');
    info.className = 'slide-info';
    const confidence = (1 - match.distance).toFixed(3);
    info.textContent = `confidence: ${confidence} · ${match.path}`;

    slide.appendChild(img);
    slide.appendChild(info);
    sliderTrack.appendChild(slide);
  });

  results.hidden = false;
  updateSlider();
}

function updateSlider() {
  const count = Math.min(matches.length, 3);
  if (!count) {
    slideStatus.textContent = '';
    return;
  }
  const clamped = Math.max(0, Math.min(activeIndex, count - 1));
  activeIndex = clamped;
  sliderTrack.style.transform = `translateX(-${activeIndex * 100}%)`;
  slideStatus.textContent = `${activeIndex + 1} / ${count}`;
}

function clampActiveIndex() {
  const count = Math.min(matches.length, 3);
  activeIndex = Math.max(0, Math.min(activeIndex, count - 1));
}

function onSliderPointerDown(event) {
  const count = Math.min(matches.length, 3);
  if (!count || count === 1 || !slider) return;
  swipeStart = {
    id: event.pointerId,
    x: event.clientX,
    y: event.clientY,
  };
  slider.setPointerCapture(event.pointerId);
}

function onSliderPointerUp(event) {
  if (!swipeStart || event.pointerId !== swipeStart.id) return;
  const deltaX = event.clientX - swipeStart.x;
  const deltaY = event.clientY - swipeStart.y;
  swipeStart = null;
  slider.releasePointerCapture(event.pointerId);
  if (Math.abs(deltaX) < 40 || Math.abs(deltaX) < Math.abs(deltaY)) {
    return;
  }
  if (deltaX < 0) {
    activeIndex += 1;
  } else {
    activeIndex -= 1;
  }
  clampActiveIndex();
  updateSlider();
}

if (slider) {
  slider.addEventListener('pointerdown', onSliderPointerDown);
  slider.addEventListener('pointerup', onSliderPointerUp);
  slider.addEventListener('pointercancel', onSliderPointerUp);
}

function drawHandles(x0, y0, x1, y1) {
  const { length, thickness } = handleMetrics();
  const corners = [
    { id: 'nw', x: x0, y: y0 },
    { id: 'ne', x: x1, y: y0 },
    { id: 'se', x: x1, y: y1 },
    { id: 'sw', x: x0, y: y1 },
  ];

  ctx.lineCap = 'round';
  ctx.lineWidth = thickness;
  ctx.strokeStyle = 'white';
  corners.forEach((corner) => drawCornerLines(corner, length));
  ctx.lineWidth = Math.max(1, thickness * 0.55);
  ctx.strokeStyle = 'black';
  corners.forEach((corner) => drawCornerLines(corner, length));
}

function render() {
  if (!currentImage) {
    return;
  }
  ctx.clearRect(0, 0, previewCanvas.width, previewCanvas.height);
  ctx.drawImage(currentImage, 0, 0);
  if (currentBBox) {
    drawBBox(currentBBox);
  }
}

function sanitizeBBox(bbox) {
  let [x0, y0, x1, y1] = bbox;
  x0 = Math.max(0, Math.min(x0, previewCanvas.width - 1));
  x1 = Math.max(0, Math.min(x1, previewCanvas.width - 1));
  y0 = Math.max(0, Math.min(y0, previewCanvas.height - 1));
  y1 = Math.max(0, Math.min(y1, previewCanvas.height - 1));
  if (x1 < x0) [x0, x1] = [x1, x0];
  if (y1 < y0) [y0, y1] = [y1, y0];
  return [x0, y0, x1, y1];
}

function canvasScale() {
  const rect = previewCanvas.getBoundingClientRect();
  return {
    scaleX: previewCanvas.width / rect.width,
    scaleY: previewCanvas.height / rect.height,
    rect,
  };
}

function hitHandle(x, y) {
  if (!currentBBox) return null;
  const [x0, y0, x1, y1] = currentBBox;
  const { length, padding } = handleMetrics();
  const handles = [
    { id: 'nw', x: x0, y: y0 },
    { id: 'ne', x: x1, y: y0 },
    { id: 'se', x: x1, y: y1 },
    { id: 'sw', x: x0, y: y1 },
  ];
  for (const h of handles) {
    const xMin = h.x - padding;
    const xMax = h.x + length + padding;
    const yMin = h.y - padding;
    const yMax = h.y + length + padding;
    if (x >= xMin && x <= xMax && y >= yMin && y <= yMax) {
      return h.id;
    }
  }
  return null;
}

function updateBBoxFromHandle(handle, x, y) {
  if (!currentBBox) return;
  let [x0, y0, x1, y1] = currentBBox;
  const offset = grabOffset || { x: 0, y: 0 };
  const adjX = x - offset.x;
  const adjY = y - offset.y;
  if (handle === 'nw') {
    x0 = adjX;
    y0 = adjY;
  } else if (handle === 'ne') {
    x1 = adjX;
    y0 = adjY;
  } else if (handle === 'se') {
    x1 = adjX;
    y1 = adjY;
  } else if (handle === 'sw') {
    x0 = adjX;
    y1 = adjY;
  }
  currentBBox = sanitizeBBox([x0, y0, x1, y1]);
  render();
}

function onPointerDown(event) {
  if (!currentBBox) return;
  const { scaleX, scaleY, rect } = canvasScale();
  const x = (event.clientX - rect.left) * scaleX;
  const y = (event.clientY - rect.top) * scaleY;
  const handle = hitHandle(x, y);
  if (!handle) return;
  activeHandle = handle;
  isDragging = true;
  lastPointer = { x, y };
  const [x0, y0, x1, y1] = currentBBox;
  let cornerX = x0;
  let cornerY = y0;
  if (handle === 'ne') {
    cornerX = x1;
    cornerY = y0;
  } else if (handle === 'se') {
    cornerX = x1;
    cornerY = y1;
  } else if (handle === 'sw') {
    cornerX = x0;
    cornerY = y1;
  }
  grabOffset = { x: x - cornerX, y: y - cornerY };
  previewCanvas.setPointerCapture(event.pointerId);
}

function onPointerMove(event) {
  if (!isDragging || !activeHandle) return;
  const { scaleX, scaleY, rect } = canvasScale();
  const x = (event.clientX - rect.left) * scaleX;
  const y = (event.clientY - rect.top) * scaleY;
  lastPointer = { x, y };
  updateBBoxFromHandle(activeHandle, x, y);
}

function onPointerUp(event) {
  if (!isDragging) return;
  isDragging = false;
  activeHandle = null;
  lastPointer = null;
  grabOffset = null;
  previewCanvas.releasePointerCapture(event.pointerId);
}

previewCanvas.addEventListener('pointerdown', onPointerDown);
previewCanvas.addEventListener('pointermove', onPointerMove);
previewCanvas.addEventListener('pointerup', onPointerUp);
previewCanvas.addEventListener('pointercancel', onPointerUp);

async function loadImageWithOrientation(file, objectUrl) {
  if (typeof createImageBitmap === 'function') {
    try {
      const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
      return { bitmap, width: bitmap.width, height: bitmap.height };
    } catch (err) {
      console.warn('createImageBitmap failed, fallback to Image()', err);
    }
  }
  const img = await new Promise((resolve, reject) => {
    const fallback = new Image();
    fallback.onload = () => resolve(fallback);
    fallback.onerror = reject;
    fallback.src = objectUrl;
  });
  return { bitmap: img, width: img.naturalWidth, height: img.naturalHeight };
}

function handleMetrics() {
  const { scaleX, scaleY, rect } = canvasScale();
  const baseDisplay = Math.min(rect.width, rect.height);
  const lengthDisplay = Math.max(28, baseDisplay * 0.08);
  const thicknessDisplay = Math.max(6, baseDisplay * 0.015);
  const paddingDisplay = Math.max(18, baseDisplay * 0.04);
  const scale = Math.max(scaleX, scaleY);
  return {
    length: lengthDisplay * scale,
    thickness: thicknessDisplay * scale,
    padding: paddingDisplay * scale,
  };
}

function drawCornerLines(corner, length) {
  const x = corner.x;
  const y = corner.y;
  if (corner.id === 'nw') {
    ctx.beginPath();
    ctx.moveTo(x, y + length);
    ctx.lineTo(x, y);
    ctx.lineTo(x + length, y);
    ctx.stroke();
  } else if (corner.id === 'ne') {
    ctx.beginPath();
    ctx.moveTo(x - length, y);
    ctx.lineTo(x, y);
    ctx.lineTo(x, y + length);
    ctx.stroke();
  } else if (corner.id === 'se') {
    ctx.beginPath();
    ctx.moveTo(x, y - length);
    ctx.lineTo(x, y);
    ctx.lineTo(x - length, y);
    ctx.stroke();
  } else if (corner.id === 'sw') {
    ctx.beginPath();
    ctx.moveTo(x + length, y);
    ctx.lineTo(x, y);
    ctx.lineTo(x, y - length);
    ctx.stroke();
  }
}
