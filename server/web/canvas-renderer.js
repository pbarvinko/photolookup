/**
 * Canvas rendering functions for drawing bboxes and guides
 */

const FILM_RATIO = 3 / 2; // 35mm: 36×24mm

/**
 * Compute 35mm film frame dimensions within a bbox
 * @param {[number, number, number, number]} bbox - Bounding box [x0, y0, x1, y1]
 * @returns {[number, number, number, number]|null} - Frame coordinates or null
 */
export function compute35mmFrame(bbox) {
  const [x0, y0, x1, y1] = bbox;
  const bw = x1 - x0;
  const bh = y1 - y0;
  if (bw <= 0 || bh <= 0) return null;
  const targetRatio = bw >= bh ? FILM_RATIO : 1 / FILM_RATIO;
  let fw, fh;
  if (bw / bh > targetRatio) {
    fh = bh;
    fw = bh * targetRatio;
  } else {
    fw = bw;
    fh = bw / targetRatio;
  }
  const cx = x0 + bw / 2;
  const cy = y0 + bh / 2;
  return [cx - fw / 2, cy - fh / 2, cx + fw / 2, cy + fh / 2];
}

/**
 * Draw corner lines for bbox handles
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {{id: string, x: number, y: number}} corner - Corner info
 * @param {number} length - Handle line length
 */
function drawCornerLines(ctx, corner, length) {
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

/**
 * Draw bbox handles at corners
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {HTMLCanvasElement} canvas - Canvas element
 * @param {number} x0 - Left x coordinate
 * @param {number} y0 - Top y coordinate
 * @param {number} x1 - Right x coordinate
 * @param {number} y1 - Bottom y coordinate
 * @param {{length: number, thickness: number}} metrics - Handle metrics
 */
export function drawHandles(ctx, canvas, x0, y0, x1, y1, metrics) {
  const { length, thickness } = metrics;
  const corners = [
    { id: 'nw', x: x0, y: y0 },
    { id: 'ne', x: x1, y: y0 },
    { id: 'se', x: x1, y: y1 },
    { id: 'sw', x: x0, y: y1 },
  ];

  ctx.lineCap = 'round';
  ctx.lineWidth = thickness;
  ctx.strokeStyle = 'white';
  corners.forEach((corner) => drawCornerLines(ctx, corner, length));
  ctx.lineWidth = Math.max(1, thickness * 0.55);
  ctx.strokeStyle = 'black';
  corners.forEach((corner) => drawCornerLines(ctx, corner, length));
}

/**
 * Draw 35mm film guide overlay
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {HTMLCanvasElement} canvas - Canvas element
 * @param {[number, number, number, number]} frame - Frame coordinates
 */
export function draw35mmGuide(ctx, canvas, frame) {
  const [fx0, fy0, fx1, fy1] = frame;
  const fw = fx1 - fx0;
  const fh = fy1 - fy0;
  const base = Math.min(canvas.width, canvas.height);
  const outer = Math.max(4, base * 0.007);
  const inner = Math.max(2, base * 0.004);
  const dashLen = Math.max(8, base * 0.018);

  ctx.save();
  ctx.lineJoin = 'round';
  ctx.setLineDash([dashLen, dashLen]);

  ctx.lineWidth = outer;
  ctx.strokeStyle = 'rgba(0, 0, 0, 0.6)';
  ctx.strokeRect(fx0, fy0, fw, fh);

  ctx.lineWidth = inner;
  ctx.strokeStyle = 'rgba(255, 180, 0, 1)';
  ctx.strokeRect(fx0, fy0, fw, fh);

  ctx.setLineDash([]);

  const fontSize = Math.max(13, base * 0.028);
  ctx.font = `bold ${fontSize}px sans-serif`;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  const tx = fx0 + outer + 3;
  const ty = fy0 + outer + 3;
  ctx.strokeStyle = 'rgba(0, 0, 0, 0.7)';
  ctx.lineWidth = 3;
  ctx.strokeText('35mm', tx, ty);
  ctx.fillStyle = 'rgba(255, 180, 0, 1)';
  ctx.fillText('35mm', tx, ty);

  ctx.restore();
}

/**
 * Draw bounding box rectangle
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {HTMLCanvasElement} canvas - Canvas element
 * @param {[number, number, number, number]} bbox - Bounding box coordinates
 * @param {{length: number, thickness: number}} handleMetrics - Handle metrics for drawing
 */
export function drawBBox(ctx, canvas, bbox, handleMetrics) {
  const [x0, y0, x1, y1] = bbox;
  const width = x1 - x0 + 1;
  const height = y1 - y0 + 1;

  ctx.lineJoin = 'round';

  const base = Math.min(canvas.width, canvas.height);
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

  drawHandles(ctx, canvas, x0, y0, x1, y1, handleMetrics);
}

/**
 * Main render function - draws image, bbox, and guides
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {HTMLCanvasElement} canvas - Canvas element
 * @param {ImageBitmap|HTMLImageElement|null} image - Image to render
 * @param {[number, number, number, number]|null} bbox - Bounding box
 * @param {{length: number, thickness: number}} handleMetrics - Handle metrics
 */
export function render(ctx, canvas, image, bbox, handleMetrics) {
  if (!image) {
    return;
  }
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(image, 0, 0);
  if (bbox) {
    const frame = compute35mmFrame(bbox);
    if (frame) draw35mmGuide(ctx, canvas, frame);
    drawBBox(ctx, canvas, bbox, handleMetrics);
  }
}
