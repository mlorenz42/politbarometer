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
    // H hat gegenüber dem reinen Halbkreis (Radius bis 184, Fußpunkt bei H-12) bewusst Luft nach oben:
    // dort sitzt die Beschriftung, wie bei den Wikipedia-Diagrammen üblich, außerhalb des Punktrings statt
    // mitten in der Punktwolke – das braucht Platz oberhalb des höchsten Sitzes, den es sonst nicht gäbe.
    var W = 380, H = 250, cx = W / 2, cy = H - 12;
    var layout = hemicycleSeats(data.gesamt), pts = layout.pts;
    // Bei wenigen Sitzen sind die Punkte (normiert layout.seatR) größer; ohne Gegenrechnung würde ihr
    // Rand über die Zeichenfläche hinausragen. R so wählen, dass Mittelpunkt-Radius + Punktradius nie
    // über den verfügbaren Platz hinausgeht (kleiner werdender Radius bei größer werdenden Punkten).
    var dotScale = 0.88;
    var R = Math.min(184, (cx - 6) / (1 + dotScale * layout.seatR));
    var dotR = Math.max(1.8, layout.seatR * R * dotScale); // etwas Luft zwischen den Punkten lassen
    var labelR = R + dotR + 16; // fester Ring außerhalb aller Punkte, unabhängig vom Winkel
    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, width: "100%", height: "auto", "aria-hidden": "true" });
    var i = 0, cum = 0, labelData = [];
    data.reihenfolge.forEach(function (k) {
      var n = data.sitze[k] || 0;
      if (!n) return;
      var isGov = govKeys.indexOf(k) >= 0;
      var g = el("g", { style: "fill:var(--s-" + k + ",var(--ink2))" + (isGov ? "" : ";opacity:.42") }, svg);
      el("title", {}, g, partyName(k) + ": " + n + " Sitz" + (n === 1 ? "" : "e") + (isGov ? " · Regierung" : ""));
      for (var s = 0; s < n; s++, i++) {
        var p = pts[i]; if (!p) continue;
        var px = cx + p.x * R, py = cy + p.y * R;
        el("circle", { cx: px.toFixed(1), cy: py.toFixed(1), r: dotR.toFixed(2) }, g);
      }
      // Winkel wie bei einem unsichtbaren Wikipedia-Farbkeil: rein proportional zum Sitzanteil (Mitte des
      // Abschnitts [cum, cum+n] von insgesamt data.gesamt Sitzen auf dem Halbkreis), NICHT der Mittelwert
      // der tatsächlichen Punktwinkel. Die echten Punkte liegen zeilenweise (verschiedene Zeilen fassen
      // unterschiedlich viele Sitze), wodurch ihr Mittelwinkel je nach Zufälligkeit der Zeilenaufteilung
      // leicht daneben liegen und wackeln kann – der Keil-Winkel ist dagegen exakt und deckungsgleich mit
      // der Fraktionsreihenfolge, unabhängig vom Packungsdetail der Punkte.
      labelData.push({ n: n, theta: Math.PI * (1 - (cum + n / 2) / data.gesamt) });
      cum += n;
    });
    // Beschriftung wie bei Wikipedias Halbkreisdiagrammen: auf dem Keilwinkel der eigenen Fraktion, aber
    // auf einem Radius außerhalb des gesamten Punktrings (labelR), statt mittendrin. Dadurch gibt es nie
    // eine Kollision mit Punkten – auch nicht mit denen fremder Fraktionen, WEIL der Winkel selbst nie
    // verändert wird (er bleibt exakt der Keilwinkel der eigenen Fraktion). Nur der Radius wird bei Bedarf
    // verkleinert, damit das Label nicht über den linken/rechten Rand der Zeichenfläche hinausragt – ein
    // Verkleinern des Winkels stattdessen (frühere Version) hätte das Label Richtung Bildmitte verschoben
    // und dabei über den Keil der Nachbarfraktion gelegt (genau der gemeldete Fehler bei kleinen
    // Randfraktionen). Bei ganz am Rand (nahe 0°/180°) sitzenden Mini-Fraktionen bleibt der vertikale
    // Abstand zur eigenen untersten Punktreihe entsprechend klein – wie auch bei Wikipedias Vorbildern,
    // wo Eck-Beschriftungen knapp neben der Spitze des eigenen Keils stehen statt hoch angehoben zu sein.
    // Alle Labels werden erst gezeichnet, nachdem alle Punkte aller Fraktionen stehen (eigener Durchlauf,
    // nicht verschachtelt mit den Punkt-Gruppen oben): sonst könnte die Punktgruppe einer später gezeich-
    // neten Nachbarfraktion – in der SVG-Zeichenreihenfolge über allem Vorherigen – das Label einer früher
    // gezeichneten Fraktion optisch verdecken, obwohl es außerhalb von deren eigenen Punkten liegt.
    if (labels) labelData.forEach(function (d) {
      var theta = d.theta, r = labelR, margin = 22;
      if (Math.cos(theta) > 1e-6) r = Math.min(r, (W - margin - cx) / Math.cos(theta));
      else if (Math.cos(theta) < -1e-6) r = Math.min(r, (margin - cx) / Math.cos(theta));
      var lx = (cx + Math.cos(theta) * r).toFixed(1);
      var ly = (cy - Math.sin(theta) * r).toFixed(1);
      var share = d.n / data.gesamt * 100, pctTxt = (share < 0.5 ? "<1" : String(Math.round(share))) + " %";
      var t = el("text", {
        x: lx, y: ly, "text-anchor": "middle",
        style: "font-variant-numeric:tabular-nums;paint-order:stroke;stroke:var(--surface);stroke-width:3px;stroke-linejoin:round",
      }, svg);
      el("tspan", { x: lx, dy: "0", style: "font-size:10.5px;font-weight:650;fill:var(--ink)" }, t, String(d.n));
      el("tspan", { x: lx, dy: "11", style: "font-size:9px;fill:var(--ink2)" }, t, pctTxt);
    });
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

  // Kürzel der stärksten Fraktion (meiste Sitze).
  function leadingParty(data) {
    var best = null, max = -1;
    data.reihenfolge.forEach(function (k) { var n = data.sitze[k] || 0; if (n > max) { max = n; best = k; } });
    return best;
  }
  // Färbt "elem" dezent in der Farbe der stärksten Fraktion ein (color-mix mit der Kartenfläche).
  function tintByLeadingParty(elem, data) {
    if (!elem) return;
    var k = leadingParty(data);
    elem.style.background = k ? "color-mix(in srgb, var(--s-" + k + ", var(--ink2)) 13%, var(--surface))" : "";
  }

  // Zeichnet Diagramm, Legende und die Infozeile in einem Aufwasch; alle drei Elemente optional.
  function renderSeats(hemiEl, legendEl, infoEl, data, partyName, govKeys) {
    if (infoEl) {
      var majority = Math.floor(data.gesamt / 2) + 1;
      infoEl.textContent = data.regierung.cab + ": " + data.regierung.sitze + " von " + data.gesamt +
        " Sitzen · Mehrheit ab " + majority + " · Stand " + fmt(ts(SITZE.stand));
    }
    if (hemiEl) { drawHemicycle(hemiEl, data, partyName, govKeys, true); tintByLeadingParty(hemiEl.closest(".card"), data); }
    if (legendEl) drawSeatLegend(legendEl, data, partyName, govKeys);
  }

  // Rendert das Halbkreisdiagramm in "container" als PNG und stößt den Download an. CSS-Variablen
  // (--s-cdu usw.) werden dabei auf feste Werte aufgelöst, da ein eigenständiges SVG die Vorlagen-
  // eigenen Custom Properties sonst nicht kennt; außerdem bekommt es einen echten Hintergrund
  // (Kartenfläche), sonst wäre das PNG transparent.
  function downloadHemicyclePNG(container, filename) {
    var live = container.querySelector("svg");
    if (!live) return;
    var clone = live.cloneNode(true);
    var liveAll = live.querySelectorAll("*"), cloneAll = clone.querySelectorAll("*");
    for (var i = 0; i < liveAll.length; i++) {
      var cs = getComputedStyle(liveAll[i]), ce = cloneAll[i];
      if (cs.fill && cs.fill !== "none") ce.setAttribute("fill", cs.fill);
      if (cs.opacity && cs.opacity !== "1") ce.setAttribute("opacity", cs.opacity);
      if (cs.stroke && cs.stroke !== "none") {
        ce.setAttribute("stroke", cs.stroke); ce.setAttribute("stroke-width", cs.strokeWidth);
        ce.setAttribute("stroke-linejoin", cs.strokeLinejoin); ce.setAttribute("paint-order", cs.paintOrder);
      }
      if (ce.tagName === "text" || ce.tagName === "tspan") { ce.setAttribute("font-size", cs.fontSize); ce.setAttribute("font-weight", cs.fontWeight); }
      // Das style-Attribut enthält noch var(--…)-Referenzen, die ein eigenständiges SVG nicht auflösen
      // kann (fällt sonst z. B. bei fill auf Schwarz zurück) – jetzt durch die Attribute oben ersetzt.
      ce.removeAttribute("style");
    }
    var vb = clone.getAttribute("viewBox").split(" ").map(Number);
    var bg = el("rect", { x: 0, y: 0, width: vb[2], height: vb[3], fill: getComputedStyle(document.documentElement).getPropertyValue("--surface").trim() || "#fff" });
    clone.insertBefore(bg, clone.firstChild);
    clone.setAttribute("font-family", "system-ui, -apple-system, 'Segoe UI', sans-serif");
    clone.removeAttribute("width"); clone.removeAttribute("height");
    var scale = 3; // schärfer als die Bildschirmauflösung
    var svgUrl = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], { type: "image/svg+xml;charset=utf-8" }));
    var img = new Image();
    img.onload = function () {
      var canvas = document.createElement("canvas");
      canvas.width = vb[2] * scale; canvas.height = vb[3] * scale;
      canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(svgUrl);
      canvas.toBlob(function (blob) {
        var a = document.createElement("a"), url = URL.createObjectURL(blob);
        a.href = url; a.download = filename;
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
        setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
      });
    };
    img.src = svgUrl;
  }
