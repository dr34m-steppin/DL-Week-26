(function () {
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const $ = (selector, root = document) => root.querySelector(selector);

  function showToast(message) {
    const toast = $("#toast");
    if (!toast || !message) return;
    toast.textContent = message;
    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), 2600);
  }

  function setupSlider() {
    const slider = $("#question-count-slider");
    const label = $("#question-count-label");
    if (!slider || !label) return;
    const sync = () => {
      label.textContent = slider.value;
    };
    slider.addEventListener("input", sync);
    sync();
  }

  function setupCoverageSelection() {
    const radios = $$("input[name='coverage_scope']");
    const selection = $("#topic-selection");
    const hidden = $("#selected-topics-input");
    const checks = $$(".topic-selector");
    if (!selection || !hidden) return;

    const syncMode = () => {
      const selectedMode = $("input[name='coverage_scope']:checked");
      const show = selectedMode && selectedMode.value === "selected";
      selection.classList.toggle("hidden", !show);
      if (!show) {
        hidden.value = "";
      }
    };

    const syncTopics = () => {
      const topics = checks.filter((c) => c.checked).map((c) => c.value.trim()).filter(Boolean);
      hidden.value = topics.join(",");
    };

    radios.forEach((radio) => radio.addEventListener("change", syncMode));
    checks.forEach((check) => check.addEventListener("change", syncTopics));

    syncMode();
    syncTopics();
  }

  function setupGenerationProgress() {
    $$(".generate-form").forEach((form) => {
      form.addEventListener("submit", () => {
        const button = $("button[type='submit']", form);
        const progress = $(".generation-progress span", form);
        if (button) {
          button.classList.add("loading");
          button.disabled = true;
        }
        if (progress) {
          let pct = 8;
          progress.style.width = pct + "%";
          const timer = window.setInterval(() => {
            pct = Math.min(92, pct + Math.max(1, Math.round((100 - pct) / 9)));
            progress.style.width = pct + "%";
            if (pct >= 92) window.clearInterval(timer);
          }, 120);
        }
      });
    });
  }

  function parseCsv(value) {
    return value
      .split(",")
      .map((v) => v.trim())
      .filter(Boolean);
  }

  function setupChipEditors() {
    $$(".chip-editor").forEach((editor) => {
      const hiddenId = editor.getAttribute("data-hidden-input");
      const hidden = hiddenId ? document.getElementById(hiddenId) : null;
      const input = $(".chip-input", editor);
      const chipList = $(".chip-list", editor);
      if (!hidden || !input || !chipList) return;

      let chips = parseCsv(hidden.value);

      const syncHidden = () => {
        hidden.value = chips.join(", ");
        hidden.dispatchEvent(new Event("change", { bubbles: true }));
      };

      const render = () => {
        chipList.innerHTML = "";
        chips.forEach((chip, idx) => {
          const tag = document.createElement("button");
          tag.type = "button";
          tag.className = "chip";
          tag.innerHTML = `<span>${chip}</span><b aria-hidden="true">×</b>`;
          tag.addEventListener("click", () => {
            chips.splice(idx, 1);
            render();
            syncHidden();
          });
          chipList.appendChild(tag);
        });
      };

      input.addEventListener("keydown", (event) => {
        if (event.key !== "Enter") return;
        event.preventDefault();
        const value = input.value.trim();
        if (!value) return;
        if (!chips.some((item) => item.toLowerCase() === value.toLowerCase())) {
          chips.push(value);
          render();
          syncHidden();
        }
        input.value = "";
      });

      render();
    });
  }

  function setupSkillCards() {
    const cards = $$(".skill-card");
    const validatedCountEl = $("#validated-count");
    const progressLabel = $("#workflow-progress-label");
    const progressBar = $("#workflow-progress-bar");
    const step3Card = document.querySelector('.workflow-step[data-step="3"]');
    const step3Pill = step3Card ? $(".status-pill", step3Card) : null;

    const totalCards = cards.length;
    const initialValidated = Number(validatedCountEl ? validatedCountEl.textContent : 0);
    const initialProgress = Number(progressLabel ? progressLabel.textContent.replace("%", "") : 0);
    const step3Initial = totalCards ? (25 * initialValidated) / totalCards : 0;
    const progressBase = Math.max(0, initialProgress - step3Initial);

    const updateProgress = () => {
      if (!validatedCountEl || !progressLabel || !progressBar) return;
      const currentValidated = $$(".validate-toggle:checked").length;
      validatedCountEl.textContent = String(currentValidated);
      const progress = Math.round(progressBase + (totalCards ? (25 * currentValidated) / totalCards : 0));
      progressLabel.textContent = `${progress}%`;
      progressBar.style.width = `${progress}%`;

      if (step3Card && step3Pill) {
        let status = "Pending";
        if (totalCards > 0 && currentValidated === totalCards) status = "Completed";
        else if (totalCards > 0) status = "In Progress";

        step3Pill.textContent = status;
        step3Pill.className = `status-pill ${status.toLowerCase().replace(/\\s+/g, "-")}`;
        step3Card.classList.remove("completed", "in-progress", "pending");
        step3Card.classList.add(status.toLowerCase().replace(/\\s+/g, "-"));
      }
    };

    cards.forEach((card) => {
      const originalTopic = (card.getAttribute("data-original-topic") || "").trim();
      const originalPrereq = (card.getAttribute("data-original-prereq") || "").trim();
      const topicInput = $(".topic-input", card);
      const hiddenPrereq = $("input[id^='prereq-hidden-']", card);
      const noteInput = $("textarea", card);
      const toggle = $(".validate-toggle", card);
      const suggestion = $(".suggestion-note", card);
      const initialNote = noteInput ? noteInput.value : "";
      const initialToggle = toggle ? toggle.checked : false;

      const recalc = () => {
        const changed =
          (topicInput && topicInput.value.trim() !== originalTopic) ||
          (hiddenPrereq && hiddenPrereq.value.trim() !== originalPrereq) ||
          (noteInput && noteInput.value !== initialNote) ||
          (toggle && toggle.checked !== initialToggle);

        card.classList.toggle("unsaved", Boolean(changed));

        const prereqChanged = hiddenPrereq && hiddenPrereq.value.trim() !== originalPrereq;
        if (suggestion) suggestion.classList.toggle("hidden", !prereqChanged);
      };

      [topicInput, hiddenPrereq, noteInput, toggle].forEach((el) => {
        if (!el) return;
        el.addEventListener("input", recalc);
        el.addEventListener("change", () => {
          recalc();
          updateProgress();
        });
      });

      const trigger = $(".accordion-trigger", card);
      const content = $(".accordion-content", card);
      if (trigger && content) {
        trigger.addEventListener("click", () => {
          const expanded = content.classList.toggle("open");
          trigger.classList.toggle("open", expanded);
          if (expanded) {
            content.style.maxHeight = content.scrollHeight + "px";
          } else {
            content.style.maxHeight = "0px";
          }
        });

        card.addEventListener("click", (event) => {
          const target = event.target;
          if (!(target instanceof Element)) return;
          if (target.closest("input, textarea, button, label, select")) return;
          trigger.click();
        });
      }

      recalc();
    });

    updateProgress();
  }

  function setupReasonDrawer() {
    const drawer = $("#reason-drawer");
    const topic = $("#drawer-topic");
    const reason = $("#drawer-reason");
    const prereq = $("#drawer-prereq");
    const close = $("#drawer-close");
    if (!drawer || !topic || !reason || !prereq || !close) return;

    $$(".reasoning-trigger").forEach((button) => {
      button.addEventListener("click", () => {
        topic.textContent = button.getAttribute("data-topic") || "AI Reasoning";
        reason.textContent = button.getAttribute("data-reason") || "No additional reasoning available.";
        prereq.textContent = `Prerequisites: ${button.getAttribute("data-prereqs") || "None"}`;
        drawer.classList.add("open");
        drawer.setAttribute("aria-hidden", "false");
      });
    });

    close.addEventListener("click", () => {
      drawer.classList.remove("open");
      drawer.setAttribute("aria-hidden", "true");
    });
  }

  function setupGraphToggle() {
    const toggle = $("#graph-toggle");
    const tableView = $("#table-view");
    const graphView = $("#graph-view");
    if (!toggle || !tableView || !graphView) return;

    toggle.addEventListener("change", () => {
      const showGraph = toggle.checked;
      tableView.classList.toggle("hidden", showGraph);
      graphView.classList.toggle("hidden", !showGraph);
      if (showGraph) renderGraph();
    });

    if (toggle.checked) renderGraph();
  }

  function syncOverrideGradeVisibility(select, wrap, manualGrade) {
    if (!select || !wrap || !manualGrade) return;
    const needsOverride = select.value === "OVERRIDDEN";
    wrap.classList.toggle("hidden", !needsOverride);
    manualGrade.required = needsOverride;
    if (!needsOverride) manualGrade.value = "";
  }

  function setupGradingDecisionForms() {
    const select = $("#decision");
    const wrap = $("#override-grade-wrap");
    const manualGrade = $("#override-grade");
    if (select && wrap && manualGrade) {
      if (!select.dataset.bound) {
        select.addEventListener("change", () => syncOverrideGradeVisibility(select, wrap, manualGrade));
        select.dataset.bound = "1";
      }
      syncOverrideGradeVisibility(select, wrap, manualGrade);
      return;
    }

    const selectors = $$(".grade-decision-select");
    selectors.forEach((legacySelect) => {
      const reviewId = legacySelect.getAttribute("data-review-id");
      const legacyWrap = reviewId ? document.getElementById(`override-grade-wrap-${reviewId}`) : null;
      const legacyManual = reviewId ? document.getElementById(`override-grade-${reviewId}`) : null;
      legacySelect.addEventListener("change", () => syncOverrideGradeVisibility(legacySelect, legacyWrap, legacyManual));
      syncOverrideGradeVisibility(legacySelect, legacyWrap, legacyManual);
    });
  }

  function applyToneClass(el, baseClass, tone) {
    if (!el) return;
    el.classList.remove(`${baseClass}-low`, `${baseClass}-medium`, `${baseClass}-high`);
    if (tone) el.classList.add(`${baseClass}-${tone}`);
  }

  function safePercent(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return "0%";
    return `${num}%`;
  }

  function setupReviewRecordBindings() {
    const dataEl = $("#review-record-data");
    if (!dataEl) return;

    let payload = {};
    try {
      payload = JSON.parse(dataEl.textContent || "{}");
    } catch (_err) {
      return;
    }

    const riskRecords = Array.isArray(payload.risk_flags) ? payload.risk_flags : [];
    const gradingRecords = Array.isArray(payload.grading_reviews) ? payload.grading_reviews : [];
    const riskById = new Map(riskRecords.map((item) => [String(item.id), item]));
    const gradingById = new Map(gradingRecords.map((item) => [String(item.id), item]));

    const riskSelect = $("#risk-record-select");
    const riskForm = $("#risk-override-form");
    const riskActionBase = riskForm ? (riskForm.getAttribute("data-action-base") || "") : "";
    const riskStudent = $("#risk-student");
    const riskTopic = $("#risk-topic");
    const riskLevel = $("#risk-level-badge");
    const riskConfidence = $("#risk-confidence");
    const riskReason = $("#risk-reason");
    const riskStatus = $("#risk-status");
    const riskNote = $("#risk-note");

    const syncRisk = () => {
      if (!riskSelect) return;
      const selectedId = String(riskSelect.value || "");
      const record = riskById.get(selectedId);
      if (!record) return;

      if (riskForm && riskActionBase) {
        riskForm.action = riskActionBase.replace("__ID__", selectedId);
      }
      if (riskStudent) riskStudent.textContent = record.student_name || "-";
      if (riskTopic) riskTopic.textContent = record.topic || "-";
      if (riskLevel) {
        riskLevel.textContent = (record.risk_level || "LOW").toUpperCase();
        applyToneClass(riskLevel, "risk", record.risk_level_class || String(record.risk_level || "low").toLowerCase());
      }
      if (riskConfidence) riskConfidence.textContent = safePercent(record.ai_confidence || 0);
      if (riskReason) riskReason.textContent = record.reason || "No reasoning available.";
      if (riskStatus) riskStatus.value = (record.status || "OPEN").toUpperCase();
      if (riskNote) riskNote.value = record.professor_override || "";
    };

    if (riskSelect) {
      riskSelect.addEventListener("change", syncRisk);
      syncRisk();
    }

    const gradingSelect = $("#grading-record-select");
    const gradingForm = $("#grading-decision-form");
    const gradingActionBase = gradingForm ? (gradingForm.getAttribute("data-action-base") || "") : "";
    const gradingStudent = $("#grading-student");
    const gradingScore = $("#grading-score");
    const gradingBadge = $("#grading-grade-badge");
    const gradingConfidence = $("#grading-confidence");
    const gradingReason = $("#grading-reason");
    const decision = $("#decision");
    const overrideGrade = $("#override-grade");
    const gradeNote = $("#grade-note");

    const normalizeDecision = (value) => {
      const normalized = String(value || "").toUpperCase();
      if (["CONFIRMED", "OVERRIDDEN", "PENDING"].includes(normalized)) return normalized;
      return "PENDING";
    };

    const syncGrading = () => {
      if (!gradingSelect) return;
      const selectedId = String(gradingSelect.value || "");
      const record = gradingById.get(selectedId);
      if (!record) return;

      if (gradingForm && gradingActionBase) {
        gradingForm.action = gradingActionBase.replace("__ID__", selectedId);
      }
      if (gradingStudent) gradingStudent.textContent = record.student_name || "-";
      if (gradingScore) {
        gradingScore.textContent = safePercent(record.score_percent || 0);
        applyToneClass(gradingScore, "grade", record.grade_class || "low");
      }
      if (gradingBadge) {
        gradingBadge.textContent = (record.ai_recommended_grade || "F").toUpperCase();
        applyToneClass(gradingBadge, "grade", record.grade_class || "low");
      }
      if (gradingConfidence) gradingConfidence.textContent = safePercent(record.ai_confidence || 0);
      if (gradingReason) gradingReason.textContent = record.ai_reason || "No reasoning available.";
      if (decision) decision.value = normalizeDecision(record.professor_decision);
      if (overrideGrade) {
        const mg = String(record.manual_grade || "").toUpperCase();
        overrideGrade.value = ["A", "B", "C", "D", "F"].includes(mg) ? mg : "";
      }
      if (gradeNote) gradeNote.value = record.professor_notes || "";

      syncOverrideGradeVisibility(decision, $("#override-grade-wrap"), overrideGrade);
    };

    if (gradingSelect) {
      gradingSelect.addEventListener("change", syncGrading);
      syncGrading();
    }
  }

  function renderGraph() {
    const svg = $("#skill-graph");
    const dataScript = $("#skill-graph-data");
    if (!svg || !dataScript) return;

    let data = {};
    try {
      data = JSON.parse(dataScript.textContent || "{}");
    } catch (_err) {
      svg.innerHTML = "";
      const txt = document.createElementNS("http://www.w3.org/2000/svg", "text");
      txt.setAttribute("x", "40");
      txt.setAttribute("y", "60");
      txt.setAttribute("fill", "#64748b");
      txt.textContent = "Unable to parse graph data. Regenerate skill map and try again.";
      svg.appendChild(txt);
      return;
    }
    const nodes = data.nodes || [];
    const edges = data.edges || [];
    svg.innerHTML = "";

    if (!nodes.length) {
      const txt = document.createElementNS("http://www.w3.org/2000/svg", "text");
      txt.setAttribute("x", "40");
      txt.setAttribute("y", "60");
      txt.setAttribute("fill", "#64748b");
      txt.textContent = "No topics yet. Generate skill map first to render graph.";
      svg.appendChild(txt);
      return;
    }

    const width = 960;
    const height = 520;
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) * 0.33;

    const colorMap = {
      NLP: "#4f46e5",
      Search: "#0891b2",
      Learning: "#059669",
      Evaluation: "#7c3aed",
      Reasoning: "#2563eb",
      Foundations: "#334155",
    };

    const byId = {};
    nodes.forEach((node, idx) => {
      const angle = (Math.PI * 2 * idx) / nodes.length;
      byId[node.id] = {
        ...node,
        x: centerX + radius * Math.cos(angle),
        y: centerY + radius * Math.sin(angle),
      };
    });

    const edgeEls = edges.map((edge) => {
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("stroke", "#cbd5e1");
      line.setAttribute("stroke-width", "1.5");
      svg.appendChild(line);
      return { edge, line };
    });

    const nodeEls = nodes.map((node) => {
      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.style.cursor = "grab";
      g.style.transition = "transform 180ms ease";

      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("r", "28");
      circle.setAttribute("fill", colorMap[node.category] || "#475569");
      circle.setAttribute("opacity", "0.95");

      const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
      label.setAttribute("text-anchor", "middle");
      label.setAttribute("dy", "4");
      label.setAttribute("font-size", "10");
      label.setAttribute("font-weight", "600");
      label.setAttribute("fill", "#ffffff");
      label.textContent = String(node.topic || "Topic").slice(0, 12);

      g.appendChild(circle);
      g.appendChild(label);
      svg.appendChild(g);

      g.addEventListener("mouseenter", () => {
        circle.setAttribute("opacity", "1");
        g.style.filter = "drop-shadow(0 10px 14px rgba(15,23,42,.18))";
      });
      g.addEventListener("mouseleave", () => {
        circle.setAttribute("opacity", "0.95");
        g.style.filter = "none";
      });

      g.addEventListener("click", () => {
        const drawer = $("#reason-drawer");
        if (!drawer) return;
        $("#drawer-topic").textContent = node.topic;
        $("#drawer-reason").textContent = node.reason || "No reasoning provided.";
        $("#drawer-prereq").textContent = `Category: ${node.category} • Confidence: ${node.confidence}%`;
        drawer.classList.add("open");
        drawer.setAttribute("aria-hidden", "false");
      });

      return { node, g };
    });

    const update = () => {
      edgeEls.forEach(({ edge, line }) => {
        const s = byId[edge.source];
        const t = byId[edge.target];
        if (!s || !t) return;
        line.setAttribute("x1", String(s.x));
        line.setAttribute("y1", String(s.y));
        line.setAttribute("x2", String(t.x));
        line.setAttribute("y2", String(t.y));
      });

      nodeEls.forEach(({ node, g }) => {
        const p = byId[node.id];
        g.setAttribute("transform", `translate(${p.x}, ${p.y})`);
      });
    };

    let dragging = null;
    let offsetX = 0;
    let offsetY = 0;

    nodeEls.forEach(({ node, g }) => {
      g.addEventListener("pointerdown", (event) => {
        dragging = node.id;
        const p = byId[node.id];
        offsetX = event.offsetX - p.x;
        offsetY = event.offsetY - p.y;
        g.setPointerCapture(event.pointerId);
      });
      g.addEventListener("pointermove", (event) => {
        if (!dragging || dragging !== node.id) return;
        byId[node.id].x = Math.max(32, Math.min(width - 32, event.offsetX - offsetX));
        byId[node.id].y = Math.max(32, Math.min(height - 32, event.offsetY - offsetY));
        update();
      });
      g.addEventListener("pointerup", () => {
        dragging = null;
      });
    });

    update();

    nodeEls.forEach(({ g }, idx) => {
      g.style.opacity = "0";
      g.style.transform += " scale(.9)";
      window.setTimeout(() => {
        g.style.transition = "opacity 180ms ease, transform 180ms ease";
        g.style.opacity = "1";
        g.style.transform = g.getAttribute("transform");
      }, 20 + idx * 28);
    });
  }

  function setupToastsAndPulse() {
    const flagsEl = $("#ui-flags");
    if (!flagsEl) return;
    const flags = JSON.parse(flagsEl.textContent || "{}");
    const map = {
      course_created: "Course created. Upload a document to begin workflow.",
      doc_uploaded: "Course document uploaded successfully.",
      skill_map_generated: "AI generated skill map from your course document.",
      skill_map_saved: "All skill-map changes saved.",
      quiz_generated: `Quiz bank generated. Estimated improvement +${flags.improvement || "0"}%`,
      quiz_updated: "Quiz question updated.",
      risk_updated: "Risk flag override applied.",
      grading_updated: "Grading decision updated.",
      grading_decision_required: "Select an instructor decision before saving.",
      override_grade_required: "Select a manual grade when overriding.",
    };

    const message = map[flags.toast] || "";
    if (message) showToast(message);

    if (flags.toast === "skill_map_generated") {
      $$(".skill-card").forEach((card, idx) => {
        window.setTimeout(() => card.classList.add("pulse"), idx * 30);
      });
    }
  }

  function setupButtonPressFx() {
    $$("button").forEach((button) => {
      button.addEventListener("pointerdown", () => button.classList.add("pressed"));
      button.addEventListener("pointerup", () => button.classList.remove("pressed"));
      button.addEventListener("pointerleave", () => button.classList.remove("pressed"));
    });
  }

  function init() {
    setupSlider();
    setupCoverageSelection();
    setupGenerationProgress();
    setupChipEditors();
    setupSkillCards();
    setupReasonDrawer();
    setupGraphToggle();
    setupReviewRecordBindings();
    setupGradingDecisionForms();
    setupToastsAndPulse();
    setupButtonPressFx();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
