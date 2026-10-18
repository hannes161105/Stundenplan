/* Erweiterung für den Stundenplan (Datei erweiterung.js, liegt neben index.html)
   1. Blendet den zweiten Physik-Praktikumsblock (14:00) aus, du hast nur den ersten (12:15 bis 13:45).
   2. Termine streichen: Der Link unter dem Plan öffnet den Bearbeiten-Modus.
      Gestrichene Termine sind rot und durchgestrichen. Die Liste liegt in gestrichen.json
      im GitHub-Repository, deshalb sehen alle Geräte dasselbe. */
(function () {
  var DATEI = "gestrichen.json";
  var DAY = 86400000;
  var bearbeiten = location.search.indexOf("bearbeiten=1") >= 0;
  var gestrichen = {};

  function $(id) { return document.getElementById(id); }
  function pad(n) { return ("0" + n).slice(-2); }
  function lsGet(k) { try { return localStorage.getItem(k) || ""; } catch (e) { return ""; } }
  function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }

  /* ---------- 1. Zweiten Physik-Block ausblenden ---------- */
  var tage = Object.keys(PLAN.events);
  for (var i = 0; i < tage.length; i++) {
    PLAN.events[tage[i]] = PLAN.events[tage[i]].filter(function (ev) {
      return !(ev.f === "physik" && ev.k === "P" && ev.s === "14:00");
    });
  }

  /* ---------- 2. Gestrichene Termine ---------- */
  // Schlüssel eines Termins: Datum|Startzeit|Titel
  function listeSetzen(liste) {
    gestrichen = {};
    for (var i = 0; i < liste.length; i++) gestrichen[liste[i]] = true;
    for (var iso in PLAN.events) {
      PLAN.events[iso].forEach(function (ev) {
        if (ev._x === undefined) ev._x = ev.x;
        ev.x = gestrichen[iso + "|" + ev.s + "|" + ev.t]
          ? "GESTRICHEN – entfällt" + (ev._x ? " · " + ev._x : "")
          : ev._x;
      });
    }
  }

  // Zeichnet den Plan neu (nutzt den vorhandenen Schalter "Pausen anzeigen", ohne ihn zu ändern)
  function neuZeichnen() { $("gap").dispatchEvent(new Event("change")); }

  function laden() {
    fetch(DATEI + "?t=" + Date.now())
      .then(function (r) { return r.ok ? r.json() : { liste: [] }; })
      .then(function (d) {
        var liste = d.liste || [];
        lsSet("sp-gestrichen", JSON.stringify(liste));
        listeSetzen(liste);
        neuZeichnen();
      })
      .catch(function () {});
  }

  function umschalten(key) {
    var token = lsGet("sp-token"), repo = lsGet("sp-repo");
    if (!token || !repo) {
      alert("Bitte oben zuerst Repository und Zugangsschlüssel eintragen und auf Speichern tippen.");
      return;
    }
    var api = "https://api.github.com/repos/" + repo + "/contents/" + DATEI;
    var kopf = { "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json" };
    var neu = [];
    fetch(api, { headers: kopf })
      .then(function (r) {
        if (r.status === 404) return {};
        if (!r.ok) throw new Error("Lesen fehlgeschlagen (" + r.status + ")");
        return r.json();
      })
      .then(function (alt) {
        var liste = [];
        if (alt.content) {
          liste = JSON.parse(decodeURIComponent(escape(atob(alt.content.replace(/\s/g, ""))))).liste || [];
        }
        var pos = liste.indexOf(key);
        if (pos >= 0) liste.splice(pos, 1); else liste.push(key);
        neu = liste;
        var body = {
          message: "Stundenplan: Termin " + (pos >= 0 ? "zurückgenommen" : "gestrichen"),
          content: btoa(unescape(encodeURIComponent(JSON.stringify({ liste: liste }, null, 1))))
        };
        if (alt.sha) body.sha = alt.sha;
        return fetch(api, { method: "PUT", headers: kopf, body: JSON.stringify(body) });
      })
      .then(function (r) {
        if (!r.ok) throw new Error("Speichern fehlgeschlagen (" + r.status + ")");
        lsSet("sp-gestrichen", JSON.stringify(neu));
        listeSetzen(neu);
        neuZeichnen();
      })
      .catch(function (e) { alert(e.message + ". Prüfe Repository und Zugangsschlüssel."); });
  }

  /* ---------- Darstellung ---------- */
  var css = document.createElement("style");
  css.textContent =
    ".ev.gestrichen{border:1.5px solid var(--alert)!important;background:transparent!important}" +
    ".ev.gestrichen .title,.ev.gestrichen .time{text-decoration:line-through;opacity:.7}" +
    ".ev.gestrichen .prog{display:none}" +
    ".sp-btn{justify-self:start;margin-top:4px;font:600 12.5px var(--font-body);padding:6px 10px;min-height:32px;" +
    "color:var(--ink);background:transparent;border:1px solid var(--line);border-radius:4px;cursor:pointer}" +
    ".sp-btn:hover{border-color:var(--alert);color:var(--alert)}" +
    ".sp-panel{display:grid;gap:8px;margin-top:14px;padding:12px;background:var(--surface);" +
    "border:1px solid var(--accent);border-radius:6px;font-size:14px}" +
    ".sp-panel input{font:14px var(--font-mono);padding:8px;color:var(--ink);background:var(--bg);" +
    "border:1px solid var(--line);border-radius:4px;width:100%;max-width:420px}" +
    ".sp-panel label{display:grid;gap:4px;color:var(--muted)}" +
    ".sp-panel a{color:var(--accent)}";
  document.head.appendChild(css);

  // Rot markieren: Karten, deren Hinweis mit GESTRICHEN beginnt
  function markieren() {
    var hinweise = document.querySelectorAll("#days .ev .warn");
    for (var i = 0; i < hinweise.length; i++) {
      if (hinweise[i].textContent.indexOf("GESTRICHEN") === 0) hinweise[i].parentNode.classList.add("gestrichen");
    }
  }

  function knopfAnlegen(karte, key) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "sp-btn";
    b.textContent = gestrichen[key] ? "Zurücknehmen" : "Streichen";
    b.addEventListener("click", function () { umschalten(key); });
    karte.appendChild(b);
  }

  // Im Bearbeiten-Modus bekommt jeder Termin einen Knopf
  function dekorieren() {
    var m = /(\d\d)\.(\d\d)\.\s*–\s*(\d\d)\.(\d\d)\.(\d{4})/.exec($("wrange").textContent);
    if (!m) return;
    var jahr = +m[5];
    if (+m[2] > +m[4]) jahr--;
    var montag = Date.UTC(jahr, +m[2] - 1, +m[1]);
    var spalten = document.querySelectorAll("#days .day");
    for (var d = 0; d < spalten.length; d++) {
      var dt = new Date(montag + d * DAY);
      var iso = dt.getUTCFullYear() + "-" + pad(dt.getUTCMonth() + 1) + "-" + pad(dt.getUTCDate());
      var karten = spalten[d].querySelectorAll(".ev");
      for (var k = 0; k < karten.length; k++) {
        if (karten[k].querySelector(".sp-btn")) continue;
        var key = iso + "|" + karten[k].getAttribute("data-s") + "|" + karten[k].querySelector(".title").textContent;
        knopfAnlegen(karten[k], key);
      }
    }
  }

  function bearbeitenPanel() {
    var host = location.hostname, teil = location.pathname.split("/");
    var standard = host.slice(-10) === ".github.io" ? host.split(".")[0] + "/" + teil[1] : "";
    var p = document.createElement("div");
    p.className = "sp-panel";
    p.innerHTML =
      "<strong>Bearbeiten-Modus</strong>" +
      "<span>Tippe bei einem Termin auf „Streichen“. Gestrichene Termine erscheinen danach auf allen Geräten rot " +
      "(kann 1–2 Minuten dauern).</span>" +
      "<label>Repository (Benutzer/Name)<input id=\"sp-repo\" autocomplete=\"off\"></label>" +
      "<label>Zugangsschlüssel (Token)<input id=\"sp-token\" type=\"password\" autocomplete=\"off\"></label>" +
      "<div><button type=\"button\" class=\"btn primary\" id=\"sp-save\">Speichern</button> " +
      "<a href=\"" + location.pathname + "\">Zurück zum Plan</a></div>";
    $("days").parentNode.insertBefore(p, $("days"));
    $("sp-repo").value = lsGet("sp-repo") || standard;
    $("sp-token").placeholder = lsGet("sp-token") ? "gespeichert (leer lassen zum Behalten)" : "hier einfügen";
    $("sp-save").addEventListener("click", function () {
      lsSet("sp-repo", $("sp-repo").value.trim());
      if ($("sp-token").value.trim()) lsSet("sp-token", $("sp-token").value.trim());
      $("sp-token").value = "";
      $("sp-token").placeholder = lsGet("sp-token") ? "gespeichert (leer lassen zum Behalten)" : "hier einfügen";
      alert("Gespeichert.");
    });
  }

  /* ---------- Start ---------- */
  var beobachter = new MutationObserver(function () {
    beobachter.disconnect();
    markieren();
    if (bearbeiten) dekorieren();
    beobachter.observe($("days"), { childList: true, subtree: true });
  });
  beobachter.observe($("days"), { childList: true, subtree: true });

  if (bearbeiten) {
    bearbeitenPanel();
  } else {
    var foot = document.querySelector(".foot");
    var link = document.createElement("p");
    link.className = "foot";
    link.innerHTML = "<a href=\"?bearbeiten=1\" target=\"_blank\" rel=\"noopener\">Termine streichen</a>";
    foot.parentNode.insertBefore(link, foot.nextSibling);
  }

  var lokal = [];
  try { lokal = JSON.parse(lsGet("sp-gestrichen") || "[]"); } catch (e) {}
  listeSetzen(lokal);
  neuZeichnen();
  laden();
})();
