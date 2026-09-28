  var ts = function (s) { var a = s.split("-"); return Date.UTC(+a[0], +a[1] - 1, +a[2]); };
  var MON = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];
  var p2 = function (n) { return (n < 10 ? "0" : "") + n; };
  var fmt = function (t) { var d = new Date(t); return p2(d.getUTCDate()) + "." + p2(d.getUTCMonth() + 1) + "." + d.getUTCFullYear(); };
  var pct = function (v) { return v == null ? "–" : String(v).replace(".", ",") + " %"; };
  var fnum = function (n) { return n == null ? "" : String(n).replace(/\B(?=(\d{3})+(?!\d))/g, "."); };
  var $ = function (id) { return document.getElementById(id); };
  var NS = "http://www.w3.org/2000/svg";
  function el(tag, attrs, parent, text) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }
  function h(tag, cls, parent, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }
  function tickList(tmin, tmax, x0, x1) {
    var span = (tmax - tmin) / 31557600000, ticks = [], y, m;
    var yearPx = (x1 - x0) / span;
    var d0 = new Date(tmin), d1 = new Date(tmax);
    if (span < 4) {
      for (y = d0.getUTCFullYear(); y <= d1.getUTCFullYear(); y++) for (m = 0; m < 12; m += 3) {
        var t = Date.UTC(y, m, 1);
        if (t >= tmin && t <= tmax) ticks.push({ t: t, label: m === 0 ? String(y) : MON[m], major: m === 0 });
      }
      if (yearPx < 130) ticks = ticks.filter(function (k) { return k.major || (new Date(k.t).getUTCMonth() === 6); });
      return ticks;
    }
    var steps = [1, 2, 4, 5, 10], step = 10;
    for (var s = 0; s < steps.length; s++) { if (steps[s] * yearPx >= 54) { step = steps[s]; break; } }
    for (y = d0.getUTCFullYear(); y <= d1.getUTCFullYear(); y++) {
      var tt = Date.UTC(y, 0, 1);
      if (tt >= tmin && tt <= tmax && y % step === 0) ticks.push({ t: tt, label: String(y), major: true });
    }
    return ticks;
  }

  var LONGMON = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"];
  function longDate(t) { var d = new Date(t); return d.getUTCDate() + ". " + LONGMON[d.getUTCMonth()] + " " + d.getUTCFullYear(); }

  // ---------- Sitzverteilung (Halbkreisdiagramm) ----------
  // Konzentrische Reihen im Abstand von zwei Sitzradien (Reihen berühren sich), Sitze innerhalb
  // einer Reihe im selben Abstand entlang des Bogens (Sitze berühren sich) – der übliche Aufbau
  // solcher Diagramme. Der Sitzradius wird per Bisektion so gesucht, dass die Kapazität knapp
  // über n liegt; überzählige Plätze fallen von innen nach außen weg, damit die äußeren Reihen
  // (wo bei den bekannten Vorbildern traditionell die Regierungsbank sitzt) voll bleiben.
  // Reihenfolge der Punkte: links (180°) nach rechts (0°), damit Parteien in der übergebenen
  // Reihenfolge zusammenhängende Blöcke bilden.
  function hemicycleCapacity(seatR, rInner, rOuter) {
    var rows = [], r = rInner;
    while (r <= rOuter + 1e-9) { rows.push(r); r += seatR * 2; }
    var counts = rows.map(function (rr) { return Math.max(1, Math.floor((Math.PI * rr) / (seatR * 2)) + 1); });
    return { rows: rows, counts: counts, total: counts.reduce(function (a, b) { return a + b; }, 0) };
  }
  function hemicycleSeats(n) {
    var rInner = 0.30, rOuter = 1, lo = 0.008, hi = 0.28;
    for (var iter = 0; iter < 30; iter++) {
      var mid = (lo + hi) / 2;
      if (hemicycleCapacity(mid, rInner, rOuter).total >= n) lo = mid; else hi = mid;
    }
    var cap = hemicycleCapacity(lo, rInner, rOuter), counts = cap.counts.slice();
    var over = cap.total - n, ri = 0, guard = 0;
    while (over > 0 && guard++ < 100000) { if (counts[ri] > 1) { counts[ri]--; over--; } ri = (ri + 1) % counts.length; }
    var pts = [];
    for (var i = 0; i < cap.rows.length; i++) {
      var cnt = counts[i], r = cap.rows[i];
      for (var s = 0; s < cnt; s++) {
        var t = cnt > 1 ? s / (cnt - 1) : 0.5, a = Math.PI - t * Math.PI;
        pts.push({ x: Math.cos(a) * r, y: -Math.sin(a) * r, a: a });
      }
    }
    pts.sort(function (p, q) { return q.a - p.a; }); // a = π (links) … 0 (rechts)
    return { pts: pts, seatR: lo };
  }

  // data: { gesamt, regierung:{cab,sitze}, reihenfolge:[Kürzel …], sitze:{Kürzel: Zahl} }
  // partyName(k) benennt ein Kürzel; govKeys sind die Kürzel der aktuellen Regierungsparteien.
  // labels: Sitzzahl und Anteil dauerhaft über jeder Fraktion einblenden (nicht nur beim Hover).
  function drawHemicycle(container, data, partyName, govKeys, labels) {
    container.textContent = "";
    var W = 380, H = labels ? 300 : 210, cx = W / 2, cy = H - 12, R = 184;
    var layout = hemicycleSeats(data.gesamt), pts = layout.pts;
    var dotR = Math.max(1.8, layout.seatR * R * 0.88); // etwas Luft zwischen den Punkten lassen
    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, width: "100%", height: "auto", "aria-hidden": "true" });
    var xy = pts.map(function (p) { return { x: cx + p.x * R, y: cy + p.y * R }; }); // einmal für alle Punkte
    var cand = []; // Beschriftungs-Kandidaten, erst nach allen Punkten gezeichnet (s. u.)
    var i = 0;
    data.reihenfolge.forEach(function (k) {
      var n = data.sitze[k] || 0;
      if (!n) return;
      var isGov = govKeys.indexOf(k) >= 0;
      var g = el("g", { style: "fill:var(--s-" + k + ",var(--ink2))" + (isGov ? "" : ";opacity:.42") }, svg);
      el("title", {}, g, partyName(k) + ": " + n + " Sitz" + (n === 1 ? "" : "e") + (isGov ? " · Regierung" : ""));
      var minY = Infinity, topXs = [];
      for (var s = 0; s < n; s++, i++) {
        var p = xy[i]; if (!p) continue;
        el("circle", { cx: p.x.toFixed(1), cy: p.y.toFixed(1), r: dotR.toFixed(2) }, g);
        // Höchsten eigenen Punkt merken (nicht die Winkelmitte: bei einer sehr breiten Fraktion,
        // die bis nah an den Scheitel reicht, läge die Beschriftung sonst mitten in den eigenen Punkten).
        if (p.y < minY - 0.5) { minY = p.y; topXs = [p.x]; } else if (p.y < minY + 0.5) topXs.push(p.x);
      }
      if (labels && topXs.length) cand.push({ n: n, lx: topXs.reduce(function (a, b) { return a + b; }, 0) / topXs.length, minY: minY });
    });
    if (labels && cand.length) {
      // "Deckenhöhe" an jeder Stelle über alle Fraktionen hinweg (nicht nur die eigene), sonst kann eine
      // Nachbarfraktion mit höher reichenden Punkten die Beschriftung verdecken.
      var win = dotR * 2.4;
      cand.forEach(function (c) {
        var ceilY = c.minY;
        xy.forEach(function (q) { if (q.y < ceilY && Math.abs(q.x - c.lx) < win) ceilY = q.y; });
        c.ceilY = ceilY;
      });
      // Liegen mehrere Beschriftungen (der Breite nach) zu dicht nebeneinander, weichen sie stufenweise
      // höher aus – bei vielen kleinen Fraktionen dicht beieinander reicht eine einzelne Ausweichstufe
      // nicht immer (klassisches Greedy-Färben: jede Beschriftung nimmt die niedrigste freie Stufe).
      var byX = cand.slice().sort(function (a, b) { return a.lx - b.lx; });
      var tiers = [];
      byX.forEach(function (c) {
        var t = 0;
        while (t < 6 && (tiers[t] || (tiers[t] = [])).some(function (x) { return Math.abs(x - c.lx) < 32; })) t++;
        tiers[t].push(c.lx); c.tier = t;
      });
      cand.forEach(function (c) {
        var ly = c.ceilY - dotR - 13 - c.tier * 23; // >= Höhe einer zweizeiligen Beschriftung, sonst verschränken sich Stufen
        var lx = Math.max(16, Math.min(W - 16, c.lx)).toFixed(1); // sonst ragen Randfraktionen über den Rand
        var anchor = c.lx < cx - R * 0.3 ? "start" : c.lx > cx + R * 0.3 ? "end" : "middle";
        var share = c.n / data.gesamt * 100, pctTxt = (share < 0.5 ? "<1" : String(Math.round(share))) + " %";
        var t = el("text", { x: lx, y: ly.toFixed(1), "text-anchor": anchor, style: "font-variant-numeric:tabular-nums" }, svg);
        el("tspan", { x: lx, dy: "0", style: "font-size:10.5px;font-weight:650;fill:var(--ink)" }, t, String(c.n));
        el("tspan", { x: lx, dy: "11", style: "font-size:9px;fill:var(--ink2)" }, t, pctTxt);
      });
    }
    container.appendChild(svg);
  }

  function drawSeatLegend(container, data, partyName, govKeys) {
    container.textContent = "";
    data.reihenfolge.forEach(function (k) {
      var n = data.sitze[k] || 0;
      if (!n) return;
      var isGov = govKeys.indexOf(k) >= 0;
      var li = h("li", isGov ? "" : "opp", container);
      h("span", "dot", li).style.background = "var(--s-" + k + ",var(--ink2))";
      h("span", "name", li, partyName(k));
      h("span", "n", li, n + " Sitz" + (n === 1 ? "" : "e"));
      if (isGov) h("span", "pill", li, "Regierung");
    });
  }

  // Zeichnet Diagramm, Legende und die Infozeile in einem Aufwasch; alle drei Elemente optional.
  function renderSeats(hemiEl, legendEl, infoEl, data, partyName, govKeys) {
    if (infoEl) {
      var majority = Math.floor(data.gesamt / 2) + 1;
      infoEl.textContent = data.regierung.cab + ": " + data.regierung.sitze + " von " + data.gesamt +
        " Sitzen · Mehrheit ab " + majority + " · Stand " + fmt(ts(SITZE.stand));
    }
    if (hemiEl) drawHemicycle(hemiEl, data, partyName, govKeys, true);
    if (legendEl) drawSeatLegend(legendEl, data, partyName, govKeys);
  }
