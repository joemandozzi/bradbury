/**
 * Bradbury — streak + tab switching
 *
 * On the day page (body.day-page):
 *   - Populates the landing streak pill from localStorage
 *   - Handles landing tab clicks → fades to reader with selected format active
 *   - Handles reader tab clicks → fades between works
 *   - Manages the "Mark tonight complete" button + streak counter
 *
 * On other pages (about, etc.): no-op except for streak display if present.
 *
 * Streak state in localStorage:
 *   bradbury_streak    : number — current consecutive-night count
 *   bradbury_last_read : string — ISO date of last completed night
 */
(function () {
  var STREAK_KEY = "bradbury_streak";
  var LAST_KEY   = "bradbury_last_read";

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

  function markRead() {
    var t = today();
    var state = getState();
    if (state.last === t) return;

    var newStreak = (!state.last)
      ? 1
      : (daysBetween(state.last, t) === 1 ? state.streak + 1 : 1);

    localStorage.setItem(STREAK_KEY, String(newStreak));
    localStorage.setItem(LAST_KEY, t);
    renderReaderStreak(newStreak);

    var btn = document.getElementById("mark-read-btn");
    if (btn) { btn.textContent = "✓ Night complete"; btn.disabled = true; }
  }

  function renderReaderStreak(streak) {
    var el = document.getElementById("streak-display");
    if (!el) return;
    el.textContent = streak > 0
      ? "🔥 " + streak + " night streak"
      : "Start your 1,000 nights tonight.";
  }

  /* ── landing ──────────────────────────────────────────── */
  function initLanding() {
    var state = getState();

    if (state.streak > 0) {
      var pill = document.getElementById("landing-streak-pill");
      var text = document.getElementById("landing-streak-text");
      if (pill && text) {
        text.textContent = state.streak + " NIGHT STREAK";
        pill.style.display = "block";
      }
    }

    document.querySelectorAll(".landing-tab").forEach(function (btn) {
      btn.addEventListener("click", function () {
        showReader(btn.dataset.format);
      });
    });
  }

  /* ── reader ───────────────────────────────────────────── */
  var activeFormat = null;

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

    var btn = document.getElementById("mark-read-btn");
    if (btn) {
      if (state.last === today()) {
        btn.textContent = "✓ Night complete";
        btn.disabled = true;
      } else {
        btn.addEventListener("click", markRead);
      }
    }

    setFormat(fmt);
  }

  function setFormat(fmt) {
    if (fmt === activeFormat) return;

    var prev = activeFormat;
    activeFormat = fmt;

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
    /* double rAF ensures browser renders opacity:0 before transitioning to 1 */
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
  }

  /* ── init ─────────────────────────────────────────────── */
  document.addEventListener("DOMContentLoaded", function () {
    if (document.body.classList.contains("day-page")) {
      initLanding();
      initReaderTabs();
    } else {
      /* non-day pages: just handle streak display if elements exist */
      var state = getState();
      renderReaderStreak(state.streak);
      var btn = document.getElementById("mark-read-btn");
      if (btn) {
        if (state.last === today()) {
          btn.textContent = "✓ Night complete";
          btn.disabled = true;
        } else {
          btn.addEventListener("click", markRead);
        }
      }
    }
  });
})();
