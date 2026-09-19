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
