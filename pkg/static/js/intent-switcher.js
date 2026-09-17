/**
 * ODACITY — Dynamic Intent-Driven Hero Engine
 * Supports 4 Intent Modes: BUY (default), RENT, LISTING, INSTITUTIONAL
 * Manages background image cross-fading, panel transitions, and sessionStorage persistence.
 */

(function () {
    'use strict';

    function initIntentEngine() {
        const intents = ['buy', 'rent', 'list', 'institutional'];

        // Elements lookup maps
        const bgs = {};
        const panels = {};
        const tabs = {};

        intents.forEach(function (intent) {
            bgs[intent] = document.getElementById('hero-bg-' + intent);
            panels[intent] = document.getElementById('hero-panel-' + intent);
            tabs[intent] = document.getElementById('btn-intent-' + intent);
        });

        // If any core panel is missing, do nothing (not homepage)
        if (!panels.buy || !panels.rent || !panels.list || !panels.institutional) {
            return;
        }

        window.setHomepageIntent = function (targetIntent) {
            const normalized = intents.includes(targetIntent) ? targetIntent : 'buy';

            intents.forEach(function (intent) {
                const isActive = (intent === normalized);

                // 1. Cross-fade Background Images
                if (bgs[intent]) {
                    bgs[intent].style.opacity = isActive ? '1' : '0';
                }

                // 2. Toggle Hero Panels
                if (panels[intent]) {
                    if (isActive) {
                        panels[intent].classList.remove('d-none');
                    } else {
                        panels[intent].classList.add('d-none');
                    }
                }

                // 3. Toggle Intent Selector Tabs
                if (tabs[intent]) {
                    if (isActive) {
                        tabs[intent].classList.add('active');
                        tabs[intent].setAttribute('aria-selected', 'true');
                    } else {
                        tabs[intent].classList.remove('active');
                        tabs[intent].setAttribute('aria-selected', 'false');
                    }
                }
            });

            // Persist intent in sessionStorage
            sessionStorage.setItem('odacity_homepage_intent', normalized);
        };

        // Attach click handlers to intent selector tabs
        intents.forEach(function (intent) {
            if (tabs[intent]) {
                tabs[intent].addEventListener('click', function (e) {
                    e.preventDefault();
                    window.setHomepageIntent(intent);
                });
            }
        });

        // Restore saved intent from sessionStorage or URL query params (default: 'buy')
        const urlParams = new URLSearchParams(window.location.search);
        const urlIntent = urlParams.get('intent');
        const savedIntent = urlIntent || sessionStorage.getItem('odacity_homepage_intent') || 'buy';

        window.setHomepageIntent(savedIntent);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initIntentEngine);
    } else {
        initIntentEngine();
    }
})();
