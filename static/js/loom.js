/* NACB "Kalahari night": generative basket-weave hero, art-form patterns, glowing cursor, figure count-up.
   Motifs are drawn from Botswana basket weaving (zigzag "flight of the swallow", triangles "knees of the tortoise").
   Everything stays still when the visitor prefers reduced motion. */
(function () {
  "use strict";
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var PALETTE = ["#f4c35a", "#f2843a", "#ff6b4a", "#63c3ec", "#9c86ff", "#e9e3ff"];

  function rand(seed) { // small deterministic generator so each card keeps its pattern
    var s = seed * 9301 + 49297;
    return function () { s = (s * 9301 + 49297) % 233280; return s / 233280; };
  }
  function fit(canvas) {
    var dpr = Math.min(window.devicePixelRatio || 1, 2), r = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.round(r.width * dpr));
    canvas.height = Math.max(1, Math.round(r.height * dpr));
    var ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx: ctx, w: r.width, h: r.height };
  }

  /* ---------- Hero loom ---------- */
  var loom = document.getElementById("loom");
  if (loom && loom.getContext) {
    var L, stars = [], mx = 0, my = 0, tx = 0, ty = 0, t0 = performance.now(), visible = true;
    var RINGS = [
      { motif: "zig", n: 36, color: 0, w: 1.6 },
      { motif: "tri", n: 28, color: 1, w: 1.4 },
      { motif: "dot", n: 48, color: 3, w: 1.2 },
      { motif: "zig", n: 24, color: 2, w: 1.8 },
      { motif: "tri", n: 18, color: 4, w: 1.4 },
      { motif: "zig", n: 14, color: 0, w: 1.6 },
      { motif: "dot", n: 20, color: 5, w: 1.0 }
    ];
    function setup() {
      L = fit(loom);
      var R = rand(7); stars = [];
      var count = Math.round(L.w * L.h / 9000);
      for (var i = 0; i < count; i++) stars.push({ x: R() * L.w, y: R() * L.h * 0.8, r: R() * 1.3 + .2, p: R() * 6.28 });
    }
    function motif(ctx, kind, r, a, size) {
      var x = Math.cos(a) * r, y = Math.sin(a) * r;
      ctx.save(); ctx.translate(x, y); ctx.rotate(a + Math.PI / 2);
      ctx.beginPath();
      if (kind === "zig") { ctx.moveTo(-size, 0); ctx.lineTo(-size / 2, -size * .8); ctx.lineTo(0, 0); ctx.lineTo(size / 2, -size * .8); ctx.lineTo(size, 0); ctx.stroke(); }
      else if (kind === "tri") { ctx.moveTo(-size * .7, size * .4); ctx.lineTo(0, -size * .7); ctx.lineTo(size * .7, size * .4); ctx.closePath(); ctx.stroke(); }
      else { ctx.arc(0, 0, size * .22, 0, 6.283); ctx.fill(); }
      ctx.restore();
    }
    function draw(now) {
      var ctx = L.ctx, w = L.w, h = L.h, t = (now - t0) / 1000;
      tx += (mx - tx) * .05; ty += (my - ty) * .05;
      ctx.clearRect(0, 0, w, h);
      for (var i = 0; i < stars.length; i++) {
        var s = stars[i], a = .35 + .35 * Math.sin(t * 1.3 + s.p);
        ctx.fillStyle = "rgba(233,227,255," + a.toFixed(3) + ")";
        ctx.beginPath(); ctx.arc(s.x + tx * 6, s.y + ty * 6, s.r, 0, 6.283); ctx.fill();
      }
      var wide = w > 760;
      var cx = wide ? w * .76 + tx * 18 : w * .82, cy = wide ? h * .46 + ty * 18 : h * .2;
      var base = Math.min(wide ? h * .5 : w * .55, 340);
      ctx.save(); ctx.translate(cx, cy);
      ctx.globalCompositeOperation = "lighter";
      var glow = ctx.createRadialGradient(0, 0, 0, 0, 0, base * 1.1);
      glow.addColorStop(0, "rgba(242,132,58,.28)"); glow.addColorStop(1, "rgba(242,132,58,0)");
      ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(0, 0, base * 1.1, 0, 6.283); ctx.fill();
      for (var k = 0; k < RINGS.length; k++) {
        var ring = RINGS[k], r = base * (1 - k / (RINGS.length + .6)), dir = k % 2 ? -1 : 1;
        var spin = t * dir * (.05 + k * .012) + (tx * .15 * dir);
        var col = PALETTE[ring.color], size = Math.max(4, r * 6.283 / ring.n * .42);
        ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineWidth = ring.w;
        ctx.globalAlpha = .55 + .3 * Math.sin(t * .8 + k);
        ctx.beginPath(); ctx.arc(0, 0, r + size * .9, 0, 6.283); ctx.lineWidth = .6; ctx.stroke(); ctx.lineWidth = ring.w;
        for (var j = 0; j < ring.n; j++) motif(ctx, ring.motif, r, spin + j * 6.283 / ring.n, size);
      }
      ctx.globalAlpha = 1; ctx.restore();
      ctx.globalCompositeOperation = "source-over";
      if (!reduce && visible) requestAnimationFrame(draw);
    }
    setup();
    window.addEventListener("resize", function () { setup(); if (reduce) draw(t0 + 4000); });
    window.addEventListener("pointermove", function (e) {
      mx = (e.clientX / window.innerWidth - .5) * 2; my = (e.clientY / window.innerHeight - .5) * 2;
    }, { passive: true });
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (es) {
        var was = visible; visible = es[0].isIntersecting;
        if (visible && !was && !reduce) requestAnimationFrame(draw);
      }).observe(loom);
    }
    if (reduce) draw(t0 + 4000); else requestAnimationFrame(draw);
  }

  /* ---------- Art-form pattern cards (drawn once) ---------- */
  function weave(canvas) {
    var F = fit(canvas), ctx = F.ctx, w = F.w, h = F.h, seed = parseInt(canvas.getAttribute("data-seed"), 10) || 1, R = rand(seed);
    var c1 = PALETTE[seed % 5], c2 = PALETTE[(seed + 2) % 5];
    var g = ctx.createLinearGradient(0, 0, w, h);
    g.addColorStop(0, "#141938"); g.addColorStop(1, seed % 2 ? "#2a1d3d" : "#10264a");
    ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
    var kind = seed % 3, step = 14 + Math.floor(R() * 10);
    ctx.lineWidth = 1.5;
    for (var y = -step, row = 0; y < h + step; y += step, row++) {
      ctx.strokeStyle = row % 3 === 0 ? c2 : c1; ctx.globalAlpha = .35 + R() * .45;
      ctx.beginPath();
      for (var x = -step, i = 0; x < w + step; x += step / 2, i++) {
        var yy = y + (kind === 0 ? (i % 2 ? -step / 2 : 0) : kind === 1 ? Math.sin(i * .9 + row) * step * .35 : (i % 4 < 2 ? 0 : -step / 2));
        if (i === 0) ctx.moveTo(x, yy); else ctx.lineTo(x, yy);
      }
      ctx.stroke();
    }
    ctx.globalAlpha = .9; ctx.fillStyle = c2;
    var cxx = w * (.6 + R() * .3), cyy = h * (.15 + R() * .3), rr = Math.min(w, h) * (.18 + R() * .1);
    var rg = ctx.createRadialGradient(cxx, cyy, 0, cxx, cyy, rr * 2.2);
    rg.addColorStop(0, c2); rg.addColorStop(1, "rgba(0,0,0,0)");
    ctx.globalAlpha = .55; ctx.fillStyle = rg; ctx.beginPath(); ctx.arc(cxx, cyy, rr * 2.2, 0, 6.283); ctx.fill();
    ctx.globalAlpha = 1;
  }
  var weaves = document.querySelectorAll(".form-weave");
  function drawWeaves() { for (var i = 0; i < weaves.length; i++) weave(weaves[i]); }
  if (weaves.length) {
    drawWeaves();
    var rt; window.addEventListener("resize", function () { clearTimeout(rt); rt = setTimeout(drawWeaves, 150); });
  }

  /* ---------- Figures count up when first seen ---------- */
  var nums = document.querySelectorAll("[data-count]");
  if (nums.length && !reduce && "IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (!e.isIntersecting) return;
        io.unobserve(e.target);
        var el = e.target, end = parseInt(el.getAttribute("data-count"), 10) || 0, start = performance.now();
        (function tick(now) {
          var p = Math.min(1, (now - start) / 1100), v = Math.round(end * (1 - Math.pow(1 - p, 3)));
          el.textContent = v; if (p < 1) requestAnimationFrame(tick);
        })(start);
      });
    });
    nums.forEach(function (n) { io.observe(n); });
  }

  /* ---------- Keep the current page's tab in view in the scrolling nav row ---------- */
  var cur = document.querySelector('.main-nav a[aria-current="page"]');
  if (cur) { var ul = cur.closest("ul"); if (ul && ul.scrollWidth > ul.clientWidth) ul.scrollLeft += cur.getBoundingClientRect().left - ul.getBoundingClientRect().left - 16; }

  /* ---------- Glowing cursor ---------- */
  var fine = window.matchMedia && window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  var dot = document.querySelector(".cursor-dot"), ring = document.querySelector(".cursor-ring");
  if (fine && !reduce && dot && ring) {
    document.documentElement.classList.add("has-cursor");
    var px = -100, py = -100, rx = -100, ry = -100, moving = false;
    function follow() {
      rx += (px - rx) * .18; ry += (py - ry) * .18;
      ring.style.transform = "translate(" + rx + "px," + ry + "px)";
      if (Math.abs(px - rx) + Math.abs(py - ry) > .3) requestAnimationFrame(follow); else moving = false;
    }
    document.addEventListener("pointermove", function (e) {
      if (e.pointerType && e.pointerType !== "mouse") return;
      px = e.clientX; py = e.clientY;
      dot.style.transform = "translate(" + px + "px," + py + "px)";
      dot.classList.remove("off"); ring.classList.remove("off");
      if (!moving) { moving = true; requestAnimationFrame(follow); }
    }, { passive: true });
    document.addEventListener("pointerover", function (e) {
      ring.classList.toggle("hot", !!(e.target.closest && e.target.closest("a, button, [role=tab], input, select, textarea, label")));
    });
    document.documentElement.addEventListener("mouseleave", function () { dot.classList.add("off"); ring.classList.add("off"); });
  }
})();
