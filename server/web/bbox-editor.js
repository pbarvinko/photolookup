/**
 * BBox editor with interactive manipulation via pointer events
 */

/**
 * Sanitize bbox to canvas bounds
 * @param {[number, number, number, number]} bbox - Bounding box
 * @param {number} width - Canvas width
 * @param {number} height - Canvas height
 * @returns {[number, number, number, number]} - Sanitized bbox
 */
export function sanitizeBBox(bbox, width, height) {
  let [x0, y0, x1, y1] = bbox;
  x0 = Math.max(0, Math.min(x0, width - 1));
  x1 = Math.max(0, Math.min(x1, width - 1));
  y0 = Math.max(0, Math.min(y0, height - 1));
  y1 = Math.max(0, Math.min(y1, height - 1));
  if (x1 < x0) [x0, x1] = [x1, x0];
  if (y1 < y0) [y0, y1] = [y1, y0];
  return [x0, y0, x1, y1];
}

/**
 * Get canvas scale factors and dimensions
 * @param {HTMLCanvasElement} canvas - Canvas element
 * @returns {{scaleX: number, scaleY: number, rect: DOMRect}}
 */
export function canvasScale(canvas) {
  const rect = canvas.getBoundingClientRect();
  return {
    scaleX: canvas.width / rect.width,
    scaleY: canvas.height / rect.height,
    rect,
  };
}

/**
 * Calculate handle metrics based on canvas size
 * @param {HTMLCanvasElement} canvas - Canvas element
 * @returns {{length: number, thickness: number, padding: number}}
 */
export function handleMetrics(canvas) {
  const { scaleX, scaleY, rect } = canvasScale(canvas);
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

/**
 * Check if pointer is over a bbox handle
 * @param {number} x - Pointer x in canvas coordinates
 * @param {number} y - Pointer y in canvas coordinates
 * @param {[number, number, number, number]} bbox - Bounding box
 * @param {{length: number, padding: number}} metrics - Handle metrics
 * @returns {string|null} - Handle id or null
 */
export function hitHandle(x, y, bbox, metrics) {
  if (!bbox) return null;
  const [x0, y0, x1, y1] = bbox;
  const { length, padding } = metrics;
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

/**
 * Setup bbox editor with interactive dragging
 * @param {HTMLCanvasElement} canvas - Canvas element
 * @param {Object} callbacks - Callback functions
 * @param {Function} callbacks.getBBox - Get current bbox
 * @param {Function} callbacks.setBBox - Set new bbox
 * @param {Function} callbacks.onBBoxChange - Called when bbox changes
 * @returns {Function} - Cleanup function to remove event listeners
 */
export function setupBBoxEditor(canvas, callbacks) {
  const { getBBox, setBBox, onBBoxChange } = callbacks;

  let activeHandle = null;
  let isDragging = false;
  let lastPointer = null;
  let grabOffset = null;

  function updateBBoxFromHandle(handle, x, y) {
    const currentBBox = getBBox();
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
    const sanitized = sanitizeBBox([x0, y0, x1, y1], canvas.width, canvas.height);
    setBBox(sanitized);
    onBBoxChange();
  }

  function onPointerDown(event) {
    const currentBBox = getBBox();
    if (!currentBBox) return;
    const { scaleX, scaleY, rect } = canvasScale(canvas);
    const x = (event.clientX - rect.left) * scaleX;
    const y = (event.clientY - rect.top) * scaleY;
    const metrics = handleMetrics(canvas);
    const handle = hitHandle(x, y, currentBBox, metrics);
    if (!handle) {
      const [bx0, by0, bx1, by1] = currentBBox;
      if (x >= bx0 && x <= bx1 && y >= by0 && y <= by1) {
        activeHandle = 'pan';
        isDragging = true;
        lastPointer = { x, y };
        canvas.setPointerCapture(event.pointerId);
      }
      return;
    }
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
    canvas.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event) {
    if (!isDragging || !activeHandle) return;
    const currentBBox = getBBox();
    const { scaleX, scaleY, rect } = canvasScale(canvas);
    const x = (event.clientX - rect.left) * scaleX;
    const y = (event.clientY - rect.top) * scaleY;
    if (activeHandle === 'pan') {
      const dx = x - lastPointer.x;
      const dy = y - lastPointer.y;
      lastPointer = { x, y };
      let [x0, y0, x1, y1] = currentBBox;
      const w = x1 - x0;
      const h = y1 - y0;
      x0 += dx;
      y0 += dy;
      x0 = Math.max(0, Math.min(x0, canvas.width - 1 - w));
      y0 = Math.max(0, Math.min(y0, canvas.height - 1 - h));
      const newBBox = [x0, y0, x0 + w, y0 + h];
      setBBox(newBBox);
      onBBoxChange();
      return;
    }
    lastPointer = { x, y };
    updateBBoxFromHandle(activeHandle, x, y);
  }

  function onPointerUp(event) {
    if (!isDragging) return;
    isDragging = false;
    activeHandle = null;
    lastPointer = null;
    grabOffset = null;
    canvas.releasePointerCapture(event.pointerId);
  }

  canvas.addEventListener('pointerdown', onPointerDown);
  canvas.addEventListener('pointermove', onPointerMove);
  canvas.addEventListener('pointerup', onPointerUp);
  canvas.addEventListener('pointercancel', onPointerUp);

  // Return cleanup function
  return () => {
    canvas.removeEventListener('pointerdown', onPointerDown);
    canvas.removeEventListener('pointermove', onPointerMove);
    canvas.removeEventListener('pointerup', onPointerUp);
    canvas.removeEventListener('pointercancel', onPointerUp);
  };
}
