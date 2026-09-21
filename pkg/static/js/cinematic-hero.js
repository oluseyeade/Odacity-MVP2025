/**
 * ==========================================================================
 * ODACITY CINEMATIC HOME HERO — UNIFIED STORY & INTENT DELEGATION ENGINE
 * ==========================================================================
 */

document.addEventListener('DOMContentLoaded', function () {
    const heroSection = document.getElementById('cinematic-home-hero');
    if (!heroSection) return;

    const frames = heroSection.querySelectorAll('.cinematic-frame');
    const dots = heroSection.querySelectorAll('.cinematic-progress-dot');
    if (!frames.length || !dots.length) return;

    let currentIndex = 0;
    let timer = null;
    const FRAME_DURATION = 6000; // 6 seconds per frame
    const CROSSFADE_DURATION = 900; // 900ms true overlapping crossfade

    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    /**
     * Switch to target frame with smooth overlapping crossfade
     */
    function goToFrame(targetIndex) {
        if (targetIndex === currentIndex && frames[targetIndex].classList.contains('active')) return;
        if (targetIndex < 0 || targetIndex >= frames.length) return;

        const previousIndex = currentIndex;
        currentIndex = targetIndex;

        frames.forEach((frame, idx) => {
            if (idx === targetIndex) {
                frame.classList.remove('exiting');
                frame.classList.add('active');
            } else if (idx === previousIndex) {
                frame.classList.remove('active');
                frame.classList.add('exiting');
                setTimeout(() => {
                    frame.classList.remove('exiting');
                }, CROSSFADE_DURATION);
            } else {
                frame.classList.remove('active', 'exiting');
            }
        });

        // Update progress dots
        dots.forEach((dot, idx) => {
            if (idx === targetIndex) {
                dot.classList.add('active');
                dot.setAttribute('aria-selected', 'true');
                const symbol = dot.querySelector('.dot-symbol');
                if (symbol) symbol.textContent = '●';
            } else {
                dot.classList.remove('active');
                dot.setAttribute('aria-selected', 'false');
                const symbol = dot.querySelector('.dot-symbol');
                if (symbol) symbol.textContent = '○';
            }
        });
    }

    /**
     * Advance to next frame
     */
    function nextFrame() {
        const nextIdx = (currentIndex + 1) % frames.length;
        goToFrame(nextIdx);
    }

    /**
     * Start auto-rotation timer
     */
    function startTimer() {
        if (prefersReducedMotion) return;
        stopTimer();
        timer = setInterval(nextFrame, FRAME_DURATION);
    }

    /**
     * Stop auto-rotation timer
     */
    function stopTimer() {
        if (timer) {
            clearInterval(timer);
            timer = null;
        }
    }

    // Attach click handlers to progress indicators
    dots.forEach((dot, idx) => {
        dot.addEventListener('click', function () {
            goToFrame(idx);
            startTimer();
        });
    });

    // Delegated click handler for intent triggers & smooth homepage navigation
    document.addEventListener('click', function (e) {
        // Handle intent triggers (e.g. data-intent-trigger="buy", "rent", "list", "institutional")
        const trigger = e.target.closest('[data-intent-trigger]');
        if (trigger) {
            const targetIntent = trigger.getAttribute('data-intent-trigger');
            if (targetIntent && typeof window.setHomepageIntent === 'function') {
                window.setHomepageIntent(targetIntent);
            }

            const href = trigger.getAttribute('href');
            if (href === '#intent-driven-section') {
                const targetSection = document.getElementById('intent-driven-section');
                if (targetSection) {
                    e.preventDefault();
                    targetSection.scrollIntoView({ behavior: 'smooth' });
                }
            }
            return;
        }

        // Handle Home links (smooth scroll to top cinematic hero)
        const homeLink = e.target.closest('a[href="#cinematic-home-hero"], a[href="#top"]');
        if (homeLink) {
            const homeHero = document.getElementById('cinematic-home-hero');
            if (homeHero) {
                e.preventDefault();
                homeHero.scrollIntoView({ behavior: 'smooth' });
            }
        }
    });

    // Pause timer on mouse enter / focus in; resume on mouse leave / focus out
    heroSection.addEventListener('mouseenter', stopTimer);
    heroSection.addEventListener('mouseleave', startTimer);
    heroSection.addEventListener('focusin', stopTimer);
    heroSection.addEventListener('focusout', startTimer);

    // Initial activation
    goToFrame(0);
    startTimer();
});
