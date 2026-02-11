/**
 * Match carousel slider functionality
 */

/**
 * Create a match slider with navigation and swipe support
 * @param {Object} elements - DOM elements
 * @param {HTMLElement} elements.resultsContainer - Results container
 * @param {HTMLElement} elements.slider - Slider element
 * @param {HTMLElement} elements.sliderTrack - Slider track
 * @param {HTMLElement} elements.slideStatus - Slide status display
 * @param {HTMLElement} elements.sliderPrev - Previous button
 * @param {HTMLElement} elements.sliderNext - Next button
 * @param {HTMLCanvasElement} elements.previewCanvas - Preview canvas for sizing
 * @returns {Object} - Slider API
 */
export function createSlider(elements) {
  const {
    resultsContainer,
    slider,
    sliderTrack,
    slideStatus,
    sliderPrev,
    sliderNext,
    previewCanvas,
  } = elements;

  let matches = [];
  let activeIndex = 0;
  let swipeStart = null;

  function clampActiveIndex() {
    const count = matches.length;
    activeIndex = Math.max(0, Math.min(activeIndex, count - 1));
  }

  function updateSlider() {
    const count = matches.length;
    if (!count) {
      slideStatus.textContent = '';
      sliderPrev.hidden = true;
      sliderNext.hidden = true;
      return;
    }
    const clamped = Math.max(0, Math.min(activeIndex, count - 1));
    activeIndex = clamped;
    sliderTrack.style.transform = `translateX(-${activeIndex * 100}%)`;
    slideStatus.textContent = `${activeIndex + 1} / ${count}`;
    sliderPrev.hidden = activeIndex === 0;
    sliderNext.hidden = activeIndex >= count - 1;
  }

  function syncSliderSize() {
    const rect = previewCanvas.getBoundingClientRect();
    if (slider) {
      slider.style.width = `${rect.width}px`;
    }
    sliderTrack.querySelectorAll('.slide img').forEach((img) => {
      img.style.height = `${rect.height}px`;
    });
  }

  function renderMatches(newMatches) {
    matches = newMatches;
    activeIndex = 0;

    if (!matches.length) {
      resultsContainer.hidden = true;
      return;
    }

    sliderTrack.innerHTML = '';
    matches.forEach((match) => {
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

    resultsContainer.hidden = false;
    syncSliderSize();
    updateSlider();
  }

  function onSliderPointerDown(event) {
    if (event.target.closest('.slider-btn')) return;
    const count = matches.length;
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

  function prevSlide() {
    activeIndex -= 1;
    clampActiveIndex();
    updateSlider();
  }

  function nextSlide() {
    activeIndex += 1;
    clampActiveIndex();
    updateSlider();
  }

  // Setup event listeners
  if (slider) {
    slider.addEventListener('pointerdown', onSliderPointerDown);
    slider.addEventListener('pointerup', onSliderPointerUp);
    slider.addEventListener('pointercancel', onSliderPointerUp);
  }

  sliderPrev.addEventListener('click', prevSlide);
  sliderNext.addEventListener('click', nextSlide);

  // Setup resize observer
  const sliderResizeObserver = new ResizeObserver(() => {
    if (!resultsContainer.hidden) {
      syncSliderSize();
    }
  });
  sliderResizeObserver.observe(previewCanvas);

  // Return public API
  return {
    renderMatches,
    updateSlider,
    reset() {
      matches = [];
      activeIndex = 0;
      sliderTrack.innerHTML = '';
      updateSlider();
    },
    getCurrentIndex() {
      return activeIndex;
    },
  };
}
