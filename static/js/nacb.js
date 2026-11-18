/* NACB Digital Platform, progressive enhancement (site works without JS). */
(function () {
  "use strict";

  // Mobile navigation toggle
  var toggle = document.querySelector(".nav-toggle");
  var nav = document.getElementById("main-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  // Draft autosave for long forms, protects work against intermittent connectivity (SRS 2.4).
  function storage() { try { return window.localStorage; } catch (e) { return null; } }
  var ls = storage();
  document.querySelectorAll("form[data-autosave]").forEach(function (form) {
    if (!ls) return;
    var key = "nacb-draft:" + form.getAttribute("data-autosave");
    var saved = {};
    try { saved = JSON.parse(ls.getItem(key) || "{}"); } catch (e) { saved = {}; }
    var restored = 0;
    form.querySelectorAll("textarea, input[type=text], input[type=number], input[type=date], input[type=url]").forEach(function (el) {
      if (!el.name || el.name === "csrfmiddlewaretoken") return;
      if (!el.value && saved[el.name]) { el.value = saved[el.name]; restored++; }
      el.addEventListener("input", function () {
        saved[el.name] = el.value;
        try { ls.setItem(key, JSON.stringify(saved)); } catch (e) { /* quota */ }
      });
    });
    if (restored) {
      var note = document.createElement("p");
      note.className = "alert alert-warning";
      note.setAttribute("role", "status");
      note.textContent = "We restored " + restored + " unsaved field(s) from this device. Review them and click Save.";
      form.insertBefore(note, form.firstChild);
    }
    form.addEventListener("submit", function () { try { ls.removeItem(key); } catch (e) { } });
  });

  // Warn about leaving a form with unsaved changes
  document.querySelectorAll("form[data-warn-unsaved]").forEach(function (form) {
    var dirty = false;
    form.addEventListener("input", function () { dirty = true; });
    form.addEventListener("submit", function () { dirty = false; });
    window.addEventListener("beforeunload", function (e) { if (dirty) { e.preventDefault(); e.returnValue = ""; } });
  });

  // Client-side file size / type check with immediate feedback
  document.querySelectorAll("input[type=file]").forEach(function (input) {
    var maxMb = parseInt(input.getAttribute("data-max-mb") || "10", 10);
    input.addEventListener("change", function () {
      var msg = input.parentNode.querySelector(".file-msg");
      if (!msg) { msg = document.createElement("span"); msg.className = "helptext file-msg"; msg.setAttribute("aria-live", "polite"); input.parentNode.appendChild(msg); }
      var f = input.files && input.files[0];
      if (!f) { msg.textContent = ""; return; }
      if (f.size > maxMb * 1048576) {
        msg.textContent = "⚠ " + f.name + " is " + (f.size / 1048576).toFixed(1) + " MB. The limit is " + maxMb + " MB.";
        msg.style.color = "#b42318"; input.value = "";
      } else {
        msg.textContent = "✓ " + f.name + " (" + (f.size / 1048576).toFixed(2) + " MB) ready to upload";
        msg.style.color = "#1f7a4d";
      }
    });
  });

  // Upload progress indicator for multipart forms
  document.querySelectorAll("form[enctype='multipart/form-data']").forEach(function (form) {
    form.addEventListener("submit", function () {
      var hasFile = Array.prototype.some.call(form.querySelectorAll("input[type=file]"), function (i) { return i.files && i.files.length; });
      if (!hasFile) return;
      var btns = form.querySelectorAll("button[type=submit]");
      btns.forEach(function (b) { b.setAttribute("aria-disabled", "true"); });
      var p = document.createElement("p");
      p.className = "alert"; p.setAttribute("role", "status");
      p.textContent = "Uploading… please keep this page open.";
      form.appendChild(p);
    });
  });

  // Budget formset: add row + live totals
  var addBtn = document.getElementById("add-budget-row");
  if (addBtn) {
    var total = document.getElementById("id_budget-TOTAL_FORMS");
    var tpl = document.getElementById("budget-empty").innerHTML;
    var body = document.getElementById("budget-rows");
    addBtn.addEventListener("click", function () {
      var n = parseInt(total.value, 10);
      var tmp = document.createElement("tbody");
      tmp.innerHTML = tpl.replace(/__prefix__/g, n);
      body.appendChild(tmp.firstElementChild);
      total.value = n + 1;
      recalc();
    });
    function recalc() {
      var sum = 0;
      body.querySelectorAll("tr").forEach(function (row) {
        var q = parseFloat((row.querySelector("[name$=quantity]") || {}).value) || 0;
        var u = parseFloat((row.querySelector("[name$=unit_cost]") || {}).value) || 0;
        var del = row.querySelector("[name$=DELETE]");
        var line = (del && del.checked) ? 0 : q * u;
        var cell = row.querySelector(".line-total");
        if (cell) cell.textContent = "P" + line.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        sum += line;
      });
      var t = document.getElementById("budget-total");
      if (t) t.textContent = "P" + sum.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    body.addEventListener("input", recalc);
    body.addEventListener("change", recalc);
    recalc();
  }

  // Character counters
  document.querySelectorAll("textarea[maxlength]").forEach(function (ta) {
    var c = document.createElement("span");
    c.className = "helptext"; c.setAttribute("aria-live", "polite");
    ta.parentNode.appendChild(c);
    function upd() { c.textContent = ta.value.length + " / " + ta.getAttribute("maxlength") + " characters"; }
    ta.addEventListener("input", upd); upd();
  });

  // Confirm dangerous actions
  document.querySelectorAll("[data-confirm]").forEach(function (el) {
    el.addEventListener("click", function (e) { if (!window.confirm(el.getAttribute("data-confirm"))) e.preventDefault(); });
  });

  // Account type toggle on sign-up form
  var typeRadios = document.querySelectorAll("input[name=account_type]");
  var orgField = document.getElementById("field-org_name");
  if (typeRadios.length && orgField) {
    var upd = function () {
      var v = document.querySelector("input[name=account_type]:checked");
      orgField.hidden = !(v && v.value === "organisation");
    };
    typeRadios.forEach(function (r) { r.addEventListener("change", upd); });
    upd();
  }
})();

/* Cookie notice: essential cookies only, so this is information + acknowledgement (stored as an essential cookie). */
(function () {
  var box = document.getElementById("cookie-notice");
  if (!box || document.cookie.indexOf("nacb_cookie_ack=1") !== -1) return;
  box.hidden = false;
  document.getElementById("cookie-ok").addEventListener("click", function () {
    document.cookie = "nacb_cookie_ack=1; max-age=31536000; path=/; SameSite=Lax";
    box.hidden = true;
  });
})();

/* Start the A to Z menu closed on small screens */
(function () {
  if (window.matchMedia("(max-width: 900px)").matches) {
    document.querySelectorAll(".az-details").forEach(function (d) { d.open = false; });
  }
})();

/* Motion: scroll reveal, count-up figures, growing bars. Skipped entirely for reduced-motion users. */
(function () {
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var main = document.getElementById("main");
  if (!main) return;

  var growers = main.querySelectorAll(".bars, .progress");
  if (reduce) {
    growers.forEach(function (g) { g.classList.add("grow"); });
    return;
  }

  // 1. Reveal content blocks as they scroll into view, staggered within each group
  var selector = ".card, .service-tile, .tile, .figures > div, .steps > li, .section-head, .table-wrap, .portfolio-grid figure, .gallery-grid figure, details.faq";
  var items = Array.prototype.filter.call(main.querySelectorAll(selector), function (el) {
    return !el.closest(".hero") && !el.parentElement.closest(selector);
  });
  items.forEach(function (el) {
    el.classList.add("reveal");
    var siblings = Array.prototype.filter.call(el.parentElement.children, function (c) { return c.matches(selector); });
    el.style.transitionDelay = Math.min(siblings.indexOf(el), 6) * 70 + "ms";
  });

  // 2. Count numbers up from zero
  function countUp(el) {
    var text = el.textContent.trim();
    if (!/^\d{1,6}$/.test(text)) return;
    var end = parseInt(text, 10), start = null, dur = 900;
    if (end === 0) return;
    // The real value is always restored, even if animation frames are paused (e.g. background tab).
    setTimeout(function () { el.textContent = end; }, dur + 150);
    function step(ts) {
      if (!start) start = ts;
      var p = Math.min((ts - start) / dur, 1);
      el.textContent = Math.round(end * (1 - Math.pow(1 - p, 3)));
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  function show(el) {
    el.classList.add("in");
    el.classList.add("grow");
  }
  // Reveal everything whose top edge has reached the screen, including anything skipped by a fast jump.
  var pending = items.slice(), pendingBars = Array.prototype.slice.call(growers), ticking = false;
  function check() {
    ticking = false;
    var limit = window.innerHeight - 10;
    pending = pending.filter(function (el) {
      if (el.getBoundingClientRect().top < limit) { show(el); return false; }
      return true;
    });
    pendingBars = pendingBars.filter(function (g) {
      if (g.getBoundingClientRect().top < limit) { g.classList.add("grow"); return false; }
      return true;
    });
    if (!pending.length && !pendingBars.length) {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    }
  }
  function onScroll() { if (!ticking) { ticking = true; setTimeout(check, 60); } }
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll);
  check();
  window.addEventListener("load", check);
})();


/* Tabs (What's on): all panels stay visible without JavaScript */
(function () {
  document.querySelectorAll("[data-tabs]").forEach(function (box) {
    var tabs = Array.prototype.slice.call(box.querySelectorAll('[role="tab"]'));
    function select(tab, focus) {
      tabs.forEach(function (t) {
        var on = t === tab, panel = document.getElementById(t.getAttribute("aria-controls"));
        t.setAttribute("aria-selected", on ? "true" : "false");
        t.tabIndex = on ? 0 : -1;
        panel.hidden = !on;
        panel.classList.toggle("shown", on);
      });
      if (focus) tab.focus();
    }
    tabs.forEach(function (t, i) {
      t.addEventListener("click", function () { select(t); });
      t.addEventListener("keydown", function (e) {
        var k = e.key, n = null;
        if (k === "ArrowRight") n = tabs[(i + 1) % tabs.length];
        if (k === "ArrowLeft") n = tabs[(i - 1 + tabs.length) % tabs.length];
        if (k === "Home") n = tabs[0];
        if (k === "End") n = tabs[tabs.length - 1];
        if (n) { e.preventDefault(); select(n, true); }
      });
    });
    select(tabs[0]);
  });
})();
