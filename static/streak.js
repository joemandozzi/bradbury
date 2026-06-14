/**
 * Bradbury — streak + tab switching
 *
 * Streak completes automatically when the user has visited all three content
 * types (poem, essay, story) AND scrolled at least 80% down the page.
 *
 * On completion the reader streak pill fades in (first time) or stays visible
 * (returning user), then its blue drop shadow pulses.
 *
 * Streak state in localStorage:
 *   bradbury_streak    : number — current consecutive-day count
 *   bradbury_last_read : string — ISO date of last completed day
 */
(function () {
  var STREAK_KEY     = "bradbury_streak";
  var LAST_KEY       = "bradbury_last_read";
  var FORMATS_NEEDED = ["story", "poem", "essay"];

  var visitedFormats = new Set();
  var hasScrolled80  = false;

  /* ── helpers ──────────────────────────────────────────── */
  function today() {
    var el = document.querySelector("[data-date]");
    return el ? el.dataset.date : new Date().toISOString().slice(0, 10);
  }

  function daysBetween(a, b) {
    return Math.round((new Date(b) - new Date(a)) / 86400000);
  }

  function getState() {
    return {
      streak: parseInt(localStorage.getItem(STREAK_KEY) || "0", 10),
      last:   localStorage.getItem(LAST_KEY) || null,
    };
  }

  function checkCompletion() {
    if (getState().last === today()) return;
    var allVisited = FORMATS_NEEDED.every(function (f) { return visitedFormats.has(f); });
    if (allVisited && hasScrolled80) markRead();
  }

  function markRead() {
    var t = today();
    var state = getState();
    if (state.last === t) return;

    var newStreak = (!state.last)
      ? 1
      : (daysBetween(state.last, t) === 1 ? state.streak + 1 : 1);

    localStorage.setItem(STREAK_KEY, String(newStreak));
    localStorage.setItem(LAST_KEY, t);
    renderLandingStreak(newStreak);
    showReaderStreakAnimated(newStreak);
  }

  /* ── streak pill rendering ────────────────────────────── */
  function renderReaderStreak(streak) {
    var pill = document.getElementById("reader-streak-pill");
    var text = document.getElementById("reader-streak-text");
    if (!pill || !text) return;
    if (streak > 0) {
      text.textContent = streak + " DAY STREAK";
      pill.style.transition = "none";
      pill.style.opacity    = "1";
      pill.style.display    = "block";
    } else {
      pill.style.display = "none";
      pill.style.opacity = "0";
    }
  }

  function showReaderStreakAnimated(streak) {
    var pill = document.getElementById("reader-streak-pill");
    var text = document.getElementById("reader-streak-text");
    if (!pill || !text) return;

    text.textContent = streak + " DAY STREAK";

    var alreadyVisible = pill.style.display === "block";

    if (alreadyVisible) {
      pulseStreakPill(pill);
    } else {
      pill.style.transition = "opacity 0.6s ease";
      pill.style.opacity    = "0";
      pill.style.display    = "block";
      requestAnimationFrame(function () {
        requestAnimationFrame(function () {
          pill.style.opacity = "1";
          setTimeout(function () { pulseStreakPill(pill); }, 650);
        });
      });
    }
  }

  function pulseStreakPill(pill) {
    pill.classList.remove("reader-streak-pill--pulse");
    void pill.offsetWidth; /* restart animation */
    pill.classList.add("reader-streak-pill--pulse");
    pill.addEventListener("animationend", function onEnd() {
      pill.classList.remove("reader-streak-pill--pulse");
      pill.removeEventListener("animationend", onEnd);
    });
  }

  function renderLandingStreak(streak) {
    var pill = document.getElementById("landing-streak-pill");
    var text = document.getElementById("landing-streak-text");
    if (!pill || !text) return;
    if (streak > 0) {
      text.textContent  = streak + " DAY STREAK";
      pill.style.display = "block";
    } else {
      pill.style.display = "none";
    }
  }

  /* ── landing ──────────────────────────────────────────── */
  function initLanding() {
    renderLandingStreak(getState().streak);

    document.querySelectorAll(".landing-tab").forEach(function (btn) {
      btn.addEventListener("click", function () {
        showReader(btn.dataset.format);
      });
    });
  }

  /* ── reader ───────────────────────────────────────────── */
  var activeFormat = null;

  function showLanding() {
    var landing = document.getElementById("landing");
    var reader  = document.getElementById("reader");
    if (!landing || !reader) return;

    reader.classList.remove("is-visible");
    document.body.classList.remove("reader-open");

    landing.style.display      = "flex";
    landing.style.pointerEvents = "";
    landing.style.opacity      = "0";
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        landing.style.opacity = "1";
      });
    });

    window.scrollTo(0, 0);
    activeFormat = null;
  }

  function showReader(fmt) {
    var landing = document.getElementById("landing");
    var reader  = document.getElementById("reader");
    if (!reader) return;

    landing.style.opacity = "0";
    landing.style.pointerEvents = "none";
    setTimeout(function () {
      landing.style.display = "none";
      document.body.classList.add("reader-open");
    }, 500);

    reader.classList.add("is-visible");

    var state = getState();
    renderReaderStreak(state.streak);
    renderLandingStreak(state.streak);

    setFormat(fmt);
  }

  function setFormat(fmt) {
    if (fmt === activeFormat) return;

    var prev = activeFormat;
    activeFormat = fmt;

    visitedFormats.add(fmt);
    checkCompletion();

    document.querySelectorAll(".reader-tab").forEach(function (tab) {
      tab.classList.toggle("is-active", tab.dataset.format === fmt);
    });

    var nextWork = document.getElementById("work-" + fmt);

    if (prev) {
      var prevWork = document.getElementById("work-" + prev);
      if (prevWork) {
        prevWork.style.opacity = "0";
        setTimeout(function () {
          prevWork.style.display = "none";
          revealWork(nextWork);
        }, 300);
        return;
      }
    }

    revealWork(nextWork);
  }

  function revealWork(el) {
    if (!el) return;
    el.style.display = "block";
    el.style.opacity = "0";
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        el.style.opacity = "1";
      });
    });
  }

  function initReaderTabs() {
    document.querySelectorAll(".reader-tab").forEach(function (btn) {
      btn.addEventListener("click", function () {
        setFormat(btn.dataset.format);
      });
    });

    // Clicking the wordmark returns to the landing
    var wordmark = document.querySelector("#reader .reader-wordmark");
    if (wordmark) {
      wordmark.style.cursor = "pointer";
      wordmark.addEventListener("click", showLanding);
    }

    // Clicking the nav background (outside any tab) returns to the landing
    var readerNav = document.querySelector(".reader-nav");
    if (readerNav) {
      readerNav.addEventListener("click", function (e) {
        if (!e.target.closest(".reader-tab")) {
          showLanding();
        }
      });
    }
  }

  function initScrollTracking() {
    window.addEventListener("scroll", function () {
      if (hasScrolled80) return;
      var scrolled = window.scrollY + window.innerHeight;
      var total    = document.documentElement.scrollHeight;
      if (scrolled / total >= 0.8) {
        hasScrolled80 = true;
        checkCompletion();
      }
    }, { passive: true });
  }

  /* ── init ─────────────────────────────────────────────── */
  document.addEventListener("DOMContentLoaded", function () {
    if (document.body.classList.contains("day-page")) {
      initLanding();
      initReaderTabs();
      initScrollTracking();
    } else {
      renderReaderStreak(getState().streak);
    }
  });
})();
