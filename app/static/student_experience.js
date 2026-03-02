(function () {
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const $ = (selector, root = document) => root.querySelector(selector);

  function setupTutorDrawer() {
    const drawer = $("#student-tutor-drawer");
    if (!drawer) return;

    const opens = $$(".tutor-open-btn");
    const close = $("#student-tutor-close");
    const form = $("#student-tutor-form", drawer);
    const indicator = $("#student-typing-indicator", drawer);
    const returnInput = $("#student-return-to", drawer);

    const openDrawer = () => {
      drawer.classList.add("open");
      drawer.setAttribute("aria-hidden", "false");
    };

    const closeDrawer = () => {
      drawer.classList.remove("open");
      drawer.setAttribute("aria-hidden", "true");
    };

    opens.forEach((btn) => btn.addEventListener("click", openDrawer));
    if (close) close.addEventListener("click", closeDrawer);

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeDrawer();
    });

    if (returnInput) {
      returnInput.value = `${window.location.pathname}${window.location.search}`;
    }

    if (form) {
      form.addEventListener("submit", () => {
        if (indicator) indicator.classList.remove("hidden");
      });
    }
  }

  function setupDashboardAnimations() {
    const cards = $$(".stagger-card");
    cards.forEach((card, idx) => {
      card.style.opacity = "0";
      card.style.transform = "translateY(10px)";
      window.setTimeout(() => {
        card.style.transition = "opacity 180ms ease, transform 180ms ease";
        card.style.opacity = "1";
        card.style.transform = "translateY(0)";
      }, idx * 100);
    });

    $$('[data-fill]').forEach((bar) => {
      const target = Number(bar.getAttribute("data-fill") || "0");
      bar.style.width = "0%";
      window.setTimeout(() => {
        bar.style.width = `${Math.max(0, Math.min(100, target))}%`;
      }, 120);
    });

    $$('[data-countup]').forEach((el) => {
      const target = Number(el.getAttribute("data-countup") || "0");
      const steps = 18;
      let current = 0;
      const inc = target / steps;
      const timer = window.setInterval(() => {
        current += inc;
        if (current >= target) {
          el.textContent = String(target);
          window.clearInterval(timer);
          return;
        }
        el.textContent = String(Math.round(current));
      }, 24);
    });
  }

  function setupAutopilotToggle() {
    const toggle = $("#autopilot-toggle");
    if (!toggle) return;

    const endpoint = toggle.getAttribute("data-endpoint");
    const label = $("#autopilot-label");
    const stateLabel = $("#learning-state-label");
    const stateReason = $("#learning-state-reason");
    const cta = $("#primary-cta-btn");

    const applyState = (enabled, payload) => {
      if (label) label.textContent = enabled ? "Learning Autopilot ON" : "Learning Autopilot OFF";
      if (stateLabel && payload?.learning_state?.label) stateLabel.textContent = payload.learning_state.label;
      if (stateReason && payload?.learning_state?.reason) stateReason.textContent = payload.learning_state.reason;
      if (cta && payload?.learning_state?.cta_href) cta.setAttribute("href", payload.learning_state.cta_href);
      if (cta && payload?.learning_state?.cta_label) cta.textContent = payload.learning_state.cta_label;
    };

    toggle.addEventListener("change", async () => {
      if (!endpoint) return;
      const enabled = toggle.checked;
      toggle.disabled = true;
      try {
        const body = new URLSearchParams();
        body.set("enabled", enabled ? "1" : "0");
        const response = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: body.toString(),
        });
        if (!response.ok) {
          throw new Error("Autopilot update failed");
        }
        const payload = await response.json();
        applyState(enabled, payload);
      } catch (_err) {
        toggle.checked = !enabled;
        applyState(toggle.checked, null);
      } finally {
        toggle.disabled = false;
      }
    });
  }

  function setupRealtimeSnapscore() {
    const el = $("#snapscore-value");
    if (!el) return;
    const endpoint = el.getAttribute("data-endpoint");
    if (!endpoint) return;

    const applyScore = (score) => {
      const value = Number(score);
      if (!Number.isFinite(value)) return;
      el.textContent = String(Math.round(value));
    };

    const fetchScore = async () => {
      try {
        const res = await fetch(endpoint, { method: "GET" });
        if (!res.ok) return;
        const data = await res.json();
        applyScore(data.score);
      } catch (_err) {
        // silent fallback
      }
    };

    fetchScore();
    window.setInterval(fetchScore, 20000);
  }

  function setupQuizPlayer() {
    const form = $("#quiz-player-form");
    if (!form) return;

    const steps = $$(".quiz-step", form);
    const prev = $("#quiz-prev", form);
    const next = $("#quiz-next", form);
    const submit = $("#quiz-submit", form);
    const label = $("#quiz-progress-label", form);
    const fill = $("#quiz-progress-fill", form);

    if (!steps.length || !prev || !next || !submit || !label || !fill) return;

    let index = 0;

    const requiredAnswered = (stepEl) => {
      const checked = $("input[type='radio']:checked", stepEl);
      return Boolean(checked);
    };

    const render = () => {
      steps.forEach((step, idx) => {
        const active = idx === index;
        step.classList.toggle("active", active);
        step.classList.toggle("hidden", !active);
      });

      label.textContent = `Q${index + 1}/${steps.length}`;
      fill.style.width = `${((index + 1) / steps.length) * 100}%`;

      prev.disabled = index === 0;
      const isLast = index === steps.length - 1;
      next.classList.toggle("hidden", isLast);
      submit.classList.toggle("hidden", !isLast);
    };

    next.addEventListener("click", () => {
      if (!requiredAnswered(steps[index])) {
        return;
      }
      index = Math.min(steps.length - 1, index + 1);
      render();
    });

    prev.addEventListener("click", () => {
      index = Math.max(0, index - 1);
      render();
    });

    $$(".quiz-option input[type='radio']", form).forEach((input) => {
      input.addEventListener("change", () => {
        const labelEl = input.closest(".quiz-option");
        if (!labelEl) return;
        const group = input.name;
        $$(`input[name='${group}']`, form).forEach((peer) => {
          const peerLabel = peer.closest(".quiz-option");
          if (peerLabel) peerLabel.classList.remove("selected");
        });
        labelEl.classList.add("selected");
      });
    });

    form.addEventListener("submit", () => {
      submit.disabled = true;
      submit.classList.add("loading");
      submit.textContent = "Submitting...";
    });

    render();
  }

  function setupTutorPageForm() {
    const form = $("#student-tutor-form-page");
    if (!form) return;
    form.addEventListener("submit", () => {
      const btn = $("button[type='submit']", form);
      if (!btn) return;
      btn.disabled = true;
      btn.textContent = "Sending...";
    });
  }

  function init() {
    setupTutorDrawer();
    setupDashboardAnimations();
    setupAutopilotToggle();
    setupRealtimeSnapscore();
    setupQuizPlayer();
    setupTutorPageForm();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
