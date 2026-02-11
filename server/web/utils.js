/**
 * Utility functions for image processing and manipulation
 */

/**
 * Load an image with proper EXIF orientation handling
 * @param {File} file - The image file
 * @param {string} objectUrl - Object URL for the file
 * @returns {Promise<{bitmap: ImageBitmap|HTMLImageElement, width: number, height: number}>}
 */
export async function loadImageWithOrientation(file, objectUrl) {
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
