/**
 * API client functions for server communication
 */

/**
 * Fetch bounding box detection for an image
 * @param {File} file - The image file
 * @returns {Promise<[number, number, number, number]|null>} - Bbox coordinates or null
 */
export async function fetchBBox(file) {
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

/**
 * Lookup similar images in the library
 * @param {File} file - The image file
 * @param {[number, number, number, number]|null} bbox - Optional bounding box
 * @returns {Promise<Object>} - Lookup results with matches
 */
export async function lookupImage(file, bbox) {
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

/**
 * Save debug information to the server
 * @param {File} file - The image file
 * @param {[number, number, number, number]|null} detected - Detected bbox
 * @param {[number, number, number, number]|null} bbox - Adjusted bbox
 * @returns {Promise<Object>} - Debug save result
 */
export async function saveDebug(file, detected, bbox) {
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

/**
 * Fetch application version from config
 * @returns {Promise<string|null>} - Version string or null
 */
export async function fetchVersion() {
  try {
    const response = await fetch('/api/config');
    if (response.ok) {
      const data = await response.json();
      return data.version || null;
    }
  } catch (err) {
    console.warn('Failed to fetch version', err);
  }
  return null;
}
