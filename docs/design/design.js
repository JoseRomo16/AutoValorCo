/*
 * AutoValor CO · design reference behaviour.
 * Theme (Claro / Auto / Oscuro), language segment (visual only in the mockup),
 * phone menu, tabs that remember the chosen vehicle across sections, and two small
 * chart renderers (interval bars, line curves) with no library.
 */
(function () {
  "use strict";

  var THEME_KEY = "autovalor.theme";
  var VEHICLE_KEY = "autovalor.vehicle";
  var root = document.documentElement;

  function read(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  function write(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* private mode */ } }

  /* ---------- Theme ---------- */
  function applyTheme(choice) {
    if (choice === "light" || choice === "dark") root.dataset.theme = choice;
    else delete root.dataset.theme;
    document.querySelectorAll("[data-theme-choice]").forEach(function (btn) {
      btn.setAttribute("aria-pressed", String(btn.dataset.themeChoice === (choice || "auto")));
    });
  }
  document.querySelectorAll("[data-theme-choice]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var choice = btn.dataset.themeChoice;
      write(THEME_KEY, choice);
      applyTheme(choice);
    });
  });
  applyTheme(read(THEME_KEY) || "auto");

  /* ---------- Language (visual in the mockup) ---------- */
  document.querySelectorAll("[data-lang-choice]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      document.querySelectorAll("[data-lang-choice]").forEach(function (other) {
        other.setAttribute("aria-pressed", String(other === btn));
      });
    });
  });

  /* ---------- Phone menu ---------- */
  var nav = document.querySelector(".nav");
  var menuBtn = document.querySelector(".menu-btn");
  if (nav && menuBtn) {
    menuBtn.addEventListener("click", function () {
      var open = nav.dataset.open === "true";
      nav.dataset.open = String(!open);
      menuBtn.setAttribute("aria-expanded", String(!open));
    });
  }

  /* ---------- Tabs (Carros / Motos), remembered across sections ---------- */
  function selectVehicle(vehicle) {
    document.querySelectorAll("[role=tablist][data-vehicle-tabs]").forEach(function (list) {
      list.querySelectorAll("[role=tab]").forEach(function (tab) {
        var on = tab.dataset.vehicle === vehicle;
        tab.setAttribute("aria-selected", String(on));
        tab.tabIndex = on ? 0 : -1;
        var panel = document.getElementById(tab.getAttribute("aria-controls"));
        if (panel) panel.hidden = !on;
      });
    });
  }
  document.querySelectorAll("[role=tablist][data-vehicle-tabs]").forEach(function (list) {
    list.addEventListener("click", function (event) {
      var tab = event.target.closest("[role=tab]");
      if (!tab) return;
      write(VEHICLE_KEY, tab.dataset.vehicle);
      selectVehicle(tab.dataset.vehicle);
    });
    list.addEventListener("keydown", function (event) {
      if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
      var tabs = Array.prototype.slice.call(list.querySelectorAll("[role=tab]"));
      var i = tabs.indexOf(document.activeElement);
      var next = tabs[(i + (event.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
      next.focus();
      next.click();
    });
  });
  if (document.querySelector("[data-vehicle-tabs]")) selectVehicle(read(VEHICLE_KEY) || "car");

  /* ---------- Formatting ---------- */
  var NBSP = " ";
  function fmt(value, digits) {
    return new Intl.NumberFormat("es-CO", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
  }
  function pct(value, digits, signed) {
    var sign = value < 0 ? "−" : signed && value > 0 ? "+" : "";
    return sign + fmt(Math.abs(value), digits === undefined ? 1 : digits) + NBSP + "%";
  }
  function pesos(value) {
    var abs = Math.abs(value);
    var sign = value < 0 ? "−" : value > 0 ? "+" : "";
    if (abs >= 1e6) return sign + "$" + fmt(abs / 1e6, 1) + NBSP + "millones";
    return sign + "$" + fmt(Math.round(abs / 1000), 0) + NBSP + "mil";
  }
  window.AV = { pct: pct, pesos: pesos, fmt: fmt };

  /* ---------- Interval bars ---------- */
  /*
   * items: [{label, sub, value, low, high, muted, ref, valueText, note}]
   * Neutral fill for magnitudes. Muted = interval crosses zero. Ref = reference category.
   */
  window.renderBars = function (el, items, opts) {
    opts = opts || {};
    var values = [];
    items.forEach(function (it) { values.push(it.value, it.low === undefined ? it.value : it.low, it.high === undefined ? it.value : it.high); });
    var min = Math.min(0, Math.min.apply(null, values));
    var max = Math.max(0, Math.max.apply(null, values));
    var pad = (max - min) * 0.05 || 1;
    if (min < 0) min -= pad;
    max += pad;
    var span = max - min;
    function pos(v) { return ((v - min) / span) * 100; }
    var zero = pos(0);

    el.classList.add("bars");
    el.innerHTML = items.map(function (it) {
      var v = pos(it.value);
      var left = Math.min(zero, v);
      var width = Math.max(Math.abs(v - zero), 0.6);
      var fillCls = it.ref ? "bar-row__fill bar-row__fill--ref" : it.muted ? "bar-row__fill bar-row__fill--muted" : "bar-row__fill";
      var ci = it.low !== undefined && !it.ref
        ? '<span class="bar-row__ci" style="left:' + pos(it.low) + "%;width:" + Math.max(pos(it.high) - pos(it.low), 0.4) + '%"></span>'
        : "";
      var zeroLine = min < 0 ? '<span class="bar-row__zero" style="left:' + zero + '%"></span>' : "";
      return (
        '<div class="bar-row' + (it.muted || it.ref ? " bar-row--muted" : "") + '">' +
          '<span class="bar-row__label">' + it.label + (it.sub ? "<em>" + it.sub + "</em>" : "") + "</span>" +
          '<span class="bar-row__track" aria-hidden="true">' + zeroLine +
            '<span class="' + fillCls + '" style="left:' + (it.ref ? zero - 0.3 : left) + "%;width:" + (it.ref ? 0.6 : width) + '%"></span>' + ci +
          "</span>" +
          '<span class="bar-row__val">' + it.valueText + (it.note ? "<span>" + it.note + "</span>" : "") + "</span>" +
        "</div>"
      );
    }).join("");
  };

  /* ---------- Line curves with end labels ---------- */
  /*
   * series: [{label, points: [[x, y]], tone: "high" | "low" | "ref"}]
   * The y axis starts near the data, not at zero, so the curves separate.
   */
  window.renderLines = function (el, series, opts) {
    opts = opts || {};
    var W = 640, H = 300, m = { t: 16, r: 150, b: 40, l: 44 };
    var xs = [], ys = [];
    series.forEach(function (s) { s.points.forEach(function (p) { xs.push(p[0]); ys.push(p[1]); }); });
    var x0 = 0, x1 = Math.max.apply(null, xs);
    var y1 = 100, y0 = Math.max(0, Math.floor((Math.min.apply(null, ys) - 5) / 10) * 10);
    function X(v) { return m.l + ((v - x0) / (x1 - x0)) * (W - m.l - m.r); }
    function Y(v) { return m.t + (1 - (v - y0) / (y1 - y0)) * (H - m.t - m.b); }
    var tone = { high: "var(--fg)", low: "var(--bad)", ref: "var(--bar)" };
    var dash = { high: "", low: "", ref: "5 4" };

    var grid = "";
    for (var g = y0; g <= y1; g += 10) {
      grid += '<line x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + Y(g) + '" y2="' + Y(g) + '"></line>';
      grid += '<text x="' + (m.l - 8) + '" y="' + (Y(g) + 4) + '" text-anchor="end">' + g + " %</text>";
    }
    var xt = "";
    [0, 2, 4, 6, 8, 10].forEach(function (t) {
      xt += '<text x="' + X(t) + '" y="' + (H - m.b + 18) + '" text-anchor="middle">' + t + "</text>";
    });

    // End labels, nudged apart so they never overlap.
    var ends = series.map(function (s) { var last = s.points[s.points.length - 1]; return { s: s, y: Y(last[1]), v: last[1] }; })
      .sort(function (a, b) { return a.y - b.y; });
    for (var i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 16) ends[i].y = ends[i - 1].y + 16;

    var lines = series.map(function (s) {
      var d = s.points.map(function (p, i) { return (i ? "L" : "M") + X(p[0]).toFixed(1) + " " + Y(p[1]).toFixed(1); }).join(" ");
      var last = s.points[s.points.length - 1];
      return '<path d="' + d + '" fill="none" stroke="' + tone[s.tone] + '" stroke-width="2.25" stroke-dasharray="' + dash[s.tone] + '"></path>' +
             '<circle cx="' + X(last[0]) + '" cy="' + Y(last[1]) + '" r="3.5" fill="' + tone[s.tone] + '"></circle>';
    }).join("");
    var labels = ends.map(function (e) {
      var last = e.s.points[e.s.points.length - 1];
      return '<text x="' + (X(last[0]) + 12) + '" y="' + (e.y + 4) + '" style="fill:var(--fg);font-size:12px">' + e.s.label +
             ' <tspan style="fill:var(--muted)">' + fmt(e.v, 0) + " %</tspan></text>";
    }).join("");

    el.innerHTML =
      '<svg class="chart" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="' + (opts.label || "") + '">' +
        '<g class="grid">' + grid + "</g>" +
        '<line class="axis" x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + Y(y0) + '" y2="' + Y(y0) + '"></line>' +
        xt + '<text x="' + ((m.l + W - m.r) / 2) + '" y="' + (H - 4) + '" text-anchor="middle">' + (opts.xLabel || "") + "</text>" +
        lines + labels +
      "</svg>";
  };
})();
