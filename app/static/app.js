/* TR Earthquake AI — Leaflet + Chart.js arayüzü
   Kural: API'den gelen tüm zamanlar UTC'dir; gösterim TR saatine çevrilir. */

const TR_TZ = "Europe/Istanbul";
const REFRESH_S = 60;

const fmtTime = (iso) =>
  new Date(iso).toLocaleString("tr-TR", { timeZone: TR_TZ, hour12: false });

const magColor = (m) =>
  m >= 7 ? "#e74c3c" : m >= 6 ? "#e67e22" : m >= 5 ? "#f1c40f" : m >= 4 ? "#e0a80d" : "#3498db";

const tileLayer = () =>
  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    attribution: "&copy; OpenStreetMap &copy; CARTO",
    maxZoom: 18,
  });

let faultsGeojson = null;
async function loadFaults() {
  if (!faultsGeojson) {
    const r = await fetch("/api/faults");
    if (r.ok) faultsGeojson = await r.json();
  }
  return faultsGeojson;
}
const faultStyle = { color: "#e74c3c", weight: 1.2, opacity: 0.55 };

/* ══════════ Görünüm geçişi ══════════ */
document.querySelectorAll(".tab").forEach((btn) =>
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const view = btn.dataset.view;
    ["live", "archive", "seismo", "compare", "impact", "validation"].forEach((v) =>
      document.getElementById(`view-${v}`).classList.toggle("hidden", v !== view)
    );
    if (view === "archive") initArchive();
    if (view === "seismo") initSeismo();
    if (view === "compare") initCompare();
    if (view === "impact") initImpact();
    if (view === "validation") initValidation();
    setTimeout(() => {
      liveMap.invalidateSize();
      archMap && archMap.invalidateSize();
      bMap && bMap.invalidateSize();
      impactMap && impactMap.invalidateSize();
    }, 60);
  })
);

/* ══════════ CANLI ══════════ */
const liveMap = L.map("map-live", { preferCanvas: true }).setView([39, 35], 6);
tileLayer().addTo(liveMap);
let liveMarkers = L.layerGroup().addTo(liveMap);
let liveFaultLayer = null;
let countdown = REFRESH_S;

async function toggleLiveFaults() {
  const on = document.getElementById("live-faults").checked;
  if (on && !liveFaultLayer) {
    const gj = await loadFaults();
    if (gj) liveFaultLayer = L.geoJSON(gj, { style: faultStyle }).addTo(liveMap);
  } else if (liveFaultLayer) {
    on ? liveFaultLayer.addTo(liveMap) : liveMap.removeLayer(liveFaultLayer);
  }
}

function kpi(label, value) {
  return `<div class="kpi"><div class="label">${label}</div><div class="value">${value}</div></div>`;
}

async function refreshLive() {
  countdown = REFRESH_S;
  const source = document.getElementById("live-source").value;
  const minMag = document.getElementById("live-minmag").value;
  let data;
  try {
    const r = await fetch(`/api/live?source=${source}&min_mag=${minMag}`);
    if (!r.ok) throw new Error(r.status);
    data = await r.json();
    setStatus(true);
  } catch {
    setStatus(false);
    return;
  }

  const quakes = data.quakes;
  const mags = quakes.map((q) => q.magnitude);
  document.getElementById("live-kpis").innerHTML =
    kpi("Son 24 Saat", `${quakes.length} deprem`) +
    kpi("En Büyük", quakes.length ? `M ${Math.max(...mags).toFixed(1)}` : "—") +
    kpi("Ortalama", quakes.length ? `M ${(mags.reduce((a, b) => a + b, 0) / mags.length).toFixed(2)}` : "—") +
    kpi("Son Güncelleme", new Date().toLocaleTimeString("tr-TR", { timeZone: TR_TZ }));

  liveMarkers.clearLayers();
  quakes.forEach((q) => {
    const c = magColor(q.magnitude);
    L.circleMarker([q.latitude, q.longitude], {
      radius: Math.max(5, q.magnitude * 2.5),
      color: c, fillColor: c, fillOpacity: 0.8, weight: 1,
    })
      .bindPopup(
        `<b>${q.location || ""}</b><br>${fmtTime(q.eventDate)}<br>` +
        `<b>M ${q.magnitude.toFixed(1)}</b> — ${Math.round(q.depth || 0)} km` +
        (q.provider ? `<br><small>Kaynak: ${q.provider}</small>` : "")
      )
      .addTo(liveMarkers);
  });

  document.getElementById("live-count").textContent = `(${quakes.length})`;
  document.getElementById("live-list").innerHTML = quakes
    .map(
      (q, i) => `
      <div class="quake-item" data-i="${i}">
        <span class="mag-badge" style="background:${magColor(q.magnitude)}">M ${q.magnitude.toFixed(1)}</span>
        <div class="quake-meta">
          <span class="quake-loc">${q.location || "—"}</span>
          <span class="quake-sub">${fmtTime(q.eventDate)} · ${Math.round(q.depth || 0)} km${q.provider ? " · " + q.provider : ""}</span>
        </div>
      </div>`
    )
    .join("");

  document.querySelectorAll(".quake-item").forEach((el) =>
    el.addEventListener("click", () => {
      const q = quakes[+el.dataset.i];
      liveMap.setView([q.latitude, q.longitude], 9);
    })
  );
}

function setStatus(ok) {
  const dot = document.getElementById("status-dot");
  dot.className = "dot " + (ok ? "ok" : "err");
  document.getElementById("status-text").textContent = ok ? "canlı veri aktif" : "kaynaklara erişilemiyor";
}

document.getElementById("live-refresh").addEventListener("click", refreshLive);
document.getElementById("live-source").addEventListener("change", refreshLive);
document.getElementById("live-minmag").addEventListener("change", refreshLive);
document.getElementById("live-faults").addEventListener("change", toggleLiveFaults);

setInterval(() => {
  countdown--;
  document.getElementById("live-countdown").textContent = `${countdown} sn sonra yenilenecek`;
  if (countdown <= 0) refreshLive();
}, 1000);

/* ══════════ ARŞİV ══════════ */
let archMap = null;
let archLayer = null;
let archFaultLayer = null;
let charts = {};
let archInited = false;

function archFilters() {
  return {
    start: document.getElementById("f-start").value,
    end: document.getElementById("f-end").value,
    min_mag: document.getElementById("f-minmag").value,
    max_mag: document.getElementById("f-maxmag").value,
    min_depth: document.getElementById("f-mindep").value,
    max_depth: document.getElementById("f-maxdep").value,
    q: document.getElementById("f-q").value.trim(),
  };
}
const qs = (obj) =>
  Object.entries(obj)
    .filter(([, v]) => v !== "" && v != null)
    .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
    .join("&");

async function initArchive() {
  if (archInited) return;
  archInited = true;
  document.getElementById("f-end").value = new Date().toISOString().slice(0, 10);
  archMap = L.map("map-archive", { preferCanvas: true }).setView([39, 35], 6);
  tileLayer().addTo(archMap);
  const gj = await loadFaults();
  if (gj) archFaultLayer = L.geoJSON(gj, { style: faultStyle }).addTo(archMap);
  document.getElementById("arch-faults").addEventListener("change", (e) => {
    if (!archFaultLayer) return;
    e.target.checked ? archFaultLayer.addTo(archMap) : archMap.removeLayer(archFaultLayer);
  });
  document.getElementById("f-apply").addEventListener("click", applyArchive);
  document.getElementById("arch-mode").addEventListener("change", applyArchive);
  await applyArchive();
}

async function applyArchive() {
  const f = archFilters();
  document.getElementById("f-csv").href = `/api/quakes?${qs({ ...f, format: "csv" })}`;

  const [quakesRes, statsRes] = await Promise.all([
    fetch(`/api/quakes?${qs(f)}&limit=5000`),
    fetch(`/api/stats?${qs(f)}`),
  ]);
  const data = await quakesRes.json();
  const stats = await statsRes.json();

  document.getElementById("arch-kpis").innerHTML = stats.total
    ? kpi("Toplam Kayıt", stats.total.toLocaleString("tr-TR")) +
      kpi("En Büyük", `M ${stats.max_mag.toFixed(1)}`) +
      kpi("Ortalama", `M ${stats.avg_mag}`) +
      kpi("Ort. Derinlik", `${stats.avg_depth} km`) +
      kpi("Aralık", `${stats.date_min} → ${stats.date_max}`)
    : kpi("Toplam Kayıt", "0");

  document.getElementById("arch-note").textContent =
    data.total > data.returned ? `${data.total.toLocaleString("tr-TR")} kayıttan en güncel ${data.returned.toLocaleString("tr-TR")} tanesi haritada` : "";

  if (archLayer) archMap.removeLayer(archLayer);
  const mode = document.getElementById("arch-mode").value;
  const quakes = data.quakes;

  if (mode === "heat") {
    archLayer = L.heatLayer(
      quakes.map((q) => [q.latitude, q.longitude, Math.pow(10, q.magnitude - 4)]),
      { radius: 12, blur: 18, gradient: { 0.2: "#3498db", 0.5: "#00e5ff", 0.7: "#f1c40f", 1.0: "#e74c3c" } }
    ).addTo(archMap);
  } else {
    archLayer = L.layerGroup(
      quakes.map((q) => {
        const c = magColor(q.magnitude);
        return L.circleMarker([q.latitude, q.longitude], {
          radius: Math.max(3, (q.magnitude - 3) * 2.2),
          color: c, fillColor: c, fillOpacity: 0.6, weight: 0.5,
        }).bindPopup(
          `<b>${q.location || ""}</b><br>${fmtTime(q.eventDate)}<br><b>M ${q.magnitude.toFixed(1)}</b> — ${Math.round(q.depth || 0)} km`
        );
      })
    ).addTo(archMap);
  }

  renderCharts(stats);
}

function renderCharts(stats) {
  if (!stats.total) return;
  const gridColor = "rgba(127,140,163,0.15)";
  const common = {
    plugins: { legend: { labels: { color: "#e6ecf5" } } },
    scales: {
      x: { ticks: { color: "#7f8ca3" }, grid: { color: gridColor } },
      y: { ticks: { color: "#7f8ca3" }, grid: { color: gridColor } },
    },
    maintainAspectRatio: false,
  };

  const mk = (id, cfg) => {
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart(document.getElementById(id), cfg);
  };

  mk("chart-yearly", {
    type: "bar",
    data: {
      labels: stats.yearly.years,
      datasets: [
        { label: "Deprem sayısı", data: stats.yearly.counts, backgroundColor: "#e74c3c88", yAxisID: "y" },
        { label: "En büyük Mw", data: stats.yearly.max_mags, type: "line", borderColor: "#f1c40f", pointRadius: 0, yAxisID: "y2" },
      ],
    },
    options: {
      ...common,
      scales: {
        ...common.scales,
        y2: { position: "right", ticks: { color: "#f1c40f" }, grid: { display: false }, min: 4, max: 9 },
      },
      plugins: { ...common.plugins, title: { display: true, text: "Yıllık Deprem Sayısı ve En Büyük Deprem", color: "#e6ecf5" } },
    },
  });

  mk("chart-mag", {
    type: "bar",
    data: { labels: stats.mag_hist.labels, datasets: [{ label: "Adet", data: stats.mag_hist.counts, backgroundColor: "#e74c3c88" }] },
    options: { ...common, plugins: { ...common.plugins, title: { display: true, text: "Büyüklük Dağılımı", color: "#e6ecf5" } } },
  });

  mk("chart-depth", {
    type: "bar",
    data: { labels: stats.depth_hist.labels, datasets: [{ label: "Adet", data: stats.depth_hist.counts, backgroundColor: "#3498db88" }] },
    options: { ...common, plugins: { ...common.plugins, title: { display: true, text: "Derinlik Dağılımı", color: "#e6ecf5" } } },
  });
}

/* ══════════ SİSMOLOJİ ══════════ */
let bMap = null;
let bCellLayer = null;
let seismoInited = false;

// b-değeri renk skalası: düşük b (büyük deprem payı yüksek) → kırmızı
function bColor(b) {
  if (b < 0.75) return "#e74c3c";
  if (b < 0.9)  return "#e67e22";
  if (b < 1.05) return "#f1c40f";
  if (b < 1.2)  return "#7fb800";
  return "#3498db";
}

async function initSeismo() {
  if (seismoInited) return;
  seismoInited = true;
  document.getElementById("s-end").value = new Date().toISOString().slice(0, 10);

  bMap = L.map("map-bvalue", { preferCanvas: true }).setView([39, 35], 5);
  tileLayer().addTo(bMap);
  const gj = await loadFaults();
  if (gj) L.geoJSON(gj, { style: { ...faultStyle, opacity: 0.3 } }).addTo(bMap);

  document.getElementById("s-apply").addEventListener("click", applySeismo);
  document.getElementById("f-forecast").addEventListener("click", runForecast);

  // Ayıklama özeti + ana şok listesi
  fetch("/api/analysis/decluster").then((r) => r.json()).then((d) => {
    document.getElementById("s-decluster-info").textContent =
      `Katalog: ${d.total.toLocaleString("tr-TR")} kayıt — %${d.aftershock_pct} artçı (GK)`;
  });
  fetch("/api/analysis/mainshocks?min_mag=6.0&since=1990-01-01").then((r) => r.json()).then((d) => {
    document.getElementById("f-mainshock").innerHTML = d.mainshocks
      .map((m) => {
        const t = m.eventDate.slice(0, 10);
        return `<option value='${JSON.stringify({ time: m.eventDate, lat: m.latitude, lon: m.longitude, mag: m.magnitude })}'>
          M ${m.magnitude.toFixed(1)} — ${(m.location || "?").slice(0, 40)} (${t})</option>`;
      })
      .join("");
  });

  await applySeismo();
  await loadBMap();
}

async function applySeismo() {
  const params = new URLSearchParams({
    start: document.getElementById("s-start").value,
    end: document.getElementById("s-end").value,
    declustered: document.getElementById("s-declustered").checked,
  });
  const r = await fetch(`/api/analysis/gr?${params}`);
  if (!r.ok) {
    document.getElementById("s-kpis").innerHTML = kpi("Hata", "Yeterli kayıt yok");
    return;
  }
  const d = await r.json();

  document.getElementById("s-kpis").innerHTML =
    kpi("b-değeri", d.fit ? `${d.fit.b} ± ${d.fit.b_err}` : "—") +
    kpi("Mc (tamlık eşiği)", d.mc != null ? `M ${d.mc.toFixed(1)}` : "—") +
    kpi("a-değeri", d.fit ? d.fit.a : "—") +
    kpi("Kayıt (M ≥ Mc)", d.fit ? d.fit.n.toLocaleString("tr-TR") : "—") +
    kpi("Toplam Kayıt", d.n_total.toLocaleString("tr-TR"));

  const gridColor = "rgba(127,140,163,0.15)";
  if (charts["chart-gr"]) charts["chart-gr"].destroy();
  charts["chart-gr"] = new Chart(document.getElementById("chart-gr"), {
    type: "scatter",
    data: {
      datasets: [
        {
          label: "Gözlenen N(≥M)",
          data: d.curve.mags.map((m, i) => ({ x: m, y: d.curve.counts[i] })),
          backgroundColor: "#3498db",
          pointRadius: 3,
        },
        ...(d.curve.fit
          ? [{
              label: `G-R fit (b=${d.fit.b})`,
              data: d.curve.fit.map((f) => ({ x: f.m, y: f.n })),
              type: "line",
              borderColor: "#e74c3c",
              pointRadius: 0,
              borderWidth: 2,
            }]
          : []),
      ],
    },
    options: {
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: "#e6ecf5" } },
        title: { display: true, text: "Gutenberg-Richter Büyüklük-Frekans İlişkisi", color: "#e6ecf5" },
      },
      scales: {
        x: { title: { display: true, text: "Büyüklük (M)", color: "#7f8ca3" }, ticks: { color: "#7f8ca3" }, grid: { color: gridColor } },
        y: { type: "logarithmic", title: { display: true, text: "N (≥M) — log", color: "#7f8ca3" }, ticks: { color: "#7f8ca3" }, grid: { color: gridColor } },
      },
    },
  });
}

async function loadBMap() {
  const r = await fetch("/api/analysis/bmap?declustered=true&cell_deg=1.0");
  if (!r.ok) return;
  const d = await r.json();
  if (bCellLayer) bMap.removeLayer(bCellLayer);
  bCellLayer = L.layerGroup(
    d.cells.map((c) => {
      const h = c.cell_deg / 2;
      return L.rectangle(
        [[c.lat - h, c.lon - h], [c.lat + h, c.lon + h]],
        { color: bColor(c.b), weight: 0.5, fillColor: bColor(c.b), fillOpacity: 0.45 }
      ).bindPopup(
        `<b>b = ${c.b} ± ${c.b_err}</b><br>Mc = M ${c.mc.toFixed(1)}<br>${c.n} deprem (M ≥ Mc)`
      );
    })
  ).addTo(bMap);
}

async function runForecast() {
  const sel = document.getElementById("f-mainshock").value;
  if (!sel) return;
  const ms = JSON.parse(sel);
  const params = new URLSearchParams({ time: ms.time, lat: ms.lat, lon: ms.lon, mag: ms.mag });
  const r = await fetch(`/api/analysis/aftershock?${params}`);
  const el = document.getElementById("forecast-result");
  if (!r.ok) {
    el.innerHTML = `<p class="muted">Tahmin hesaplanamadı.</p>`;
    return;
  }
  const d = await r.json();

  let html = `<p class="muted">Dizi: ${d.sequence_events.toLocaleString("tr-TR")} kayıt ·
    geçen süre ${Math.round(d.elapsed_days)} gün · b=${d.b_value}${d.b_source === "fallback" ? " (bölgesel varsayılan)" : ""}
    ${d.omori ? ` · Omori: p=${d.omori.p}, c=${d.omori.c}` : ""}</p>`;

  if (!d.forecast) {
    html += `<p>${d.note || "Bu dizi için tahmin üretilemedi."}</p>`;
  } else {
    const horizons = [...new Set(d.forecast.map((f) => f.horizon_days))];
    const mags = [...new Set(d.forecast.map((f) => f.min_mag))];
    const probCls = (p) => (p >= 0.5 ? "prob-high" : p >= 0.1 ? "prob-mid" : "prob-low");
    html += `<table class="forecast-table"><tr><th></th>${mags.map((m) => `<th>M ≥ ${m.toFixed(0)}</th>`).join("")}</tr>`;
    horizons.forEach((h) => {
      html += `<tr><th>Önümüzdeki ${h} gün</th>`;
      mags.forEach((m) => {
        const f = d.forecast.find((x) => x.horizon_days === h && x.min_mag === m);
        html += `<td class="${probCls(f.probability)}">%${(f.probability * 100).toFixed(1)}<br><small class="muted">~${f.expected.toFixed(2)} adet</small></td>`;
      });
      html += `</tr>`;
    });
    html += `</table>
      <p class="muted" style="margin-top:8px">En az bir M≥m artçı olasılığı (Reasenberg-Jones).
      Dizi ne kadar eskiyse olasılıklar o kadar düşer — bu beklenen davranıştır.</p>`;
  }
  el.innerHTML = html;
}

/* ══════════ KAYNAK KARŞILAŞTIRMA ══════════ */
let compareInited = false;

function initCompare() {
  if (compareInited) return;
  compareInited = true;
  document.getElementById("c-apply").addEventListener("click", runCompare);
  runCompare();
}

async function runCompare() {
  const note = document.getElementById("c-note");
  note.textContent = "Sorgulanıyor…";
  const params = new URLSearchParams({
    start: document.getElementById("c-start").value,
    end: document.getElementById("c-end").value,
    min_mag: document.getElementById("c-minmag").value,
    samples: 60,
  });

  let d;
  try {
    const r = await fetch(`/api/compare?${params}`);
    if (!r.ok) throw new Error(r.status);
    d = await r.json();
  } catch {
    note.textContent = "Kaynaklara erişilemedi.";
    return;
  }
  note.textContent = d.notes.length ? d.notes[0] : "";

  const cmp = d.comparisons[0];
  const st = cmp ? cmp.stats : null;
  const cat = Object.fromEntries(d.catalogs.map((c) => [c.source, c]));

  document.getElementById("c-kpis").innerHTML =
    kpi("AFAD kaydı", (cat.AFAD?.count ?? 0).toLocaleString("tr-TR")) +
    kpi("USGS kaydı", (cat.USGS?.count ?? 0).toLocaleString("tr-TR")) +
    kpi("Eşleşen olay", cmp ? cmp.matched.toLocaleString("tr-TR") : "—") +
    kpi("Yalnız AFAD'da", cmp ? cmp.only_a.toLocaleString("tr-TR") : "—") +
    kpi("Yalnız USGS'te", cmp ? cmp.only_b.toLocaleString("tr-TR") : "—") +
    kpi("Medyan büyüklük farkı", st ? `${st.dmag_median > 0 ? "+" : ""}${st.dmag_median}` : "—") +
    kpi("Medyan episantr farkı", st ? `${st.dist_median} km` : "—") +
    kpi("En büyük episantr farkı", st ? `${st.dist_max} km` : "—");

  const pairs = d.pairs || [];
  drawCompareCharts(pairs);
  drawScales(cmp);
  drawPairTable(pairs);
}

function drawCompareCharts(pairs) {
  const gridColor = "rgba(127,140,163,0.15)";
  const common = {
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { color: "#7f8ca3" }, grid: { color: gridColor } },
      y: { ticks: { color: "#7f8ca3" }, grid: { color: gridColor } },
    },
  };
  const mk = (id, cfg) => {
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart(document.getElementById(id), cfg);
  };

  // Büyüklük farkı histogramı
  const bins = {};
  pairs.forEach((p) => {
    const b = (Math.round(p.dmag * 10) / 10).toFixed(1);
    bins[b] = (bins[b] || 0) + 1;
  });
  const labels = Object.keys(bins).sort((a, b) => a - b);
  mk("chart-dmag", {
    type: "bar",
    data: {
      labels,
      datasets: [{
        data: labels.map((l) => bins[l]),
        backgroundColor: labels.map((l) => (Math.abs(+l) < 0.05 ? "#7fb80088" : "#e74c3c88")),
      }],
    },
    options: {
      ...common,
      plugins: {
        ...common.plugins,
        title: { display: true, text: "Büyüklük Farkı Dağılımı (AFAD − USGS)", color: "#e6ecf5" },
      },
    },
  });

  // Büyüklük vs episantr farkı
  mk("chart-dist", {
    type: "scatter",
    data: {
      datasets: [{
        data: pairs.map((p) => ({ x: Math.max(p.mag_a, p.mag_b), y: p.dist_km })),
        backgroundColor: "#3498db",
        pointRadius: 4,
      }],
    },
    options: {
      ...common,
      scales: {
        x: { ...common.scales.x, title: { display: true, text: "Büyüklük", color: "#7f8ca3" } },
        y: { ...common.scales.y, title: { display: true, text: "Episantr farkı (km)", color: "#7f8ca3" } },
      },
      plugins: {
        ...common.plugins,
        title: { display: true, text: "Episantr Farkı — Büyüklüğe Göre", color: "#e6ecf5" },
      },
    },
  });
}

function drawScales(cmp) {
  const el = document.getElementById("c-scales");
  if (!cmp || !cmp.scale_pairs.length) {
    el.innerHTML = `<p class="muted">Ölçek kırılımı için yeterli eşleşme yok.</p>`;
    return;
  }
  el.innerHTML = `<table class="forecast-table">
    <tr><th>AFAD / USGS ölçeği</th><th>Eşleşme</th><th>Ortalama fark</th><th>Medyan fark</th></tr>
    ${cmp.scale_pairs.map((s) => `<tr>
      <td><b>${s.pair}</b></td>
      <td>${s.n}</td>
      <td class="${Math.abs(s.dmag_mean) >= 0.2 ? "prob-mid" : "prob-low"}">${s.dmag_mean > 0 ? "+" : ""}${s.dmag_mean.toFixed(2)}</td>
      <td>${s.dmag_median > 0 ? "+" : ""}${s.dmag_median.toFixed(2)}</td>
    </tr>`).join("")}
  </table>
  <p class="muted" style="margin-top:8px">Pozitif değer AFAD'ın daha büyük ölçtüğünü gösterir.
  Ölçekler farklı fiziksel büyüklükler ölçer; sistematik fark beklenen bir durumdur.</p>`;
}

function drawPairTable(pairs) {
  const el = document.getElementById("c-pairs");
  if (!pairs.length) {
    el.innerHTML = `<p class="muted">Bu pencerede eşleşen olay bulunamadı.</p>`;
    return;
  }
  el.innerHTML = `<table class="forecast-table">
    <tr><th>Zaman (TSİ)</th><th>AFAD</th><th>USGS</th><th>Fark</th><th>Episantr</th><th>Zaman farkı</th><th>Yer</th></tr>
    ${pairs.map((p) => `<tr${p.ambiguous ? ' class="ambiguous"' : ""}>
      <td>${fmtTime(p.time_a)}</td>
      <td><b>M ${p.mag_a.toFixed(1)}</b> <span class="muted">${p.magtype_a || "?"}</span></td>
      <td><b>M ${p.mag_b.toFixed(1)}</b> <span class="muted">${p.magtype_b || "?"}</span></td>
      <td class="${Math.abs(p.dmag) >= 0.3 ? "prob-mid" : "prob-low"}">${p.dmag > 0 ? "+" : ""}${p.dmag.toFixed(1)}</td>
      <td>${p.dist_km.toFixed(1)} km</td>
      <td>${p.dt_s.toFixed(0)} sn</td>
      <td class="loc-cell">${(p.location_a || "").slice(0, 34)}</td>
    </tr>`).join("")}
  </table>
  <p class="muted" style="margin-top:8px">Sarı satırlar, tolerans penceresinde birden fazla aday
  bulunduğu için eşleşmesi belirsiz olan olaylardır.</p>`;
}

/* ══════════ ETKİ ANALİZİ ══════════ */
let impactMap = null;
let impactLayer = null;
let shelterLayer = null;
let impactInited = false;
let lastImpact = null;

async function initImpact() {
  if (impactInited) return;
  impactInited = true;
  impactMap = L.map("map-impact", { preferCanvas: true }).setView([39.5, 33], 6);
  tileLayer().addTo(impactMap);
  const gj = await loadFaults();
  if (gj) L.geoJSON(gj, { style: { ...faultStyle, opacity: 0.3 } }).addTo(impactMap);

  document.getElementById("i-apply").addEventListener("click", runImpact);
  document.getElementById("i-shelters").addEventListener("change", toggleShelters);
  document.getElementById("i-event").addEventListener("change", (e) => {
    if (!e.target.value) return;
    const ev = JSON.parse(e.target.value);
    document.getElementById("i-mag").value = ev.magnitude;
    document.getElementById("i-lat").value = ev.latitude.toFixed(3);
    document.getElementById("i-lon").value = ev.longitude.toFixed(3);
    document.getElementById("i-depth").value = Math.max(1, Math.round(ev.depth || 10));
    runImpact();
  });

  fetch("/api/analysis/mainshocks?min_mag=6.5&limit=40")
    .then((r) => r.json())
    .then((d) => {
      document.getElementById("i-event").insertAdjacentHTML(
        "beforeend",
        d.mainshocks
          .map((m) => `<option value='${JSON.stringify(m)}'>M ${m.magnitude.toFixed(1)} — ${(m.location || "?").slice(0, 36)} (${m.eventDate.slice(0, 10)})</option>`)
          .join("")
      );
    });

  await runImpact();
}

async function runImpact() {
  const p = new URLSearchParams({
    mag: document.getElementById("i-mag").value,
    lat: document.getElementById("i-lat").value,
    lon: document.getElementById("i-lon").value,
    depth: document.getElementById("i-depth").value,
  });
  const r = await fetch(`/api/impact?${p}`);
  if (!r.ok) {
    document.getElementById("i-kpis").innerHTML = kpi("Hata", "Hesaplanamadı");
    return;
  }
  const d = await r.json();
  lastImpact = d;

  const strong = d.bands.find((b) => b.mmi_min === 7.0);
  document.getElementById("i-kpis").innerHTML =
    kpi("En yüksek şiddet", d.max_mmi ? `MMI ${d.max_mmi.toFixed(1)}` : "—") +
    kpi("Etkilenen yerleşim", d.total_settlements.toLocaleString("tr-TR")) +
    kpi("Yaklaşık nüfus", `~${(d.total_population / 1e6).toFixed(1)} milyon`) +
    kpi("MMI VII+ nüfus", strong ? `~${(strong.population / 1e6).toFixed(1)} milyon` : "yok");

  document.getElementById("i-bands").innerHTML = d.bands.length
    ? d.bands
        .slice()
        .reverse()
        .map(
          (b) => `
      <div class="band-row">
        <span class="band-chip" style="background:${b.color}">${b.roman}</span>
        <div class="band-meta">
          <span class="band-label">${b.label}</span>
          <span class="muted">${b.settlements} yerleşim · ~${(b.population / 1e6).toFixed(2)} milyon kişi${b.radius_km ? ` · ~${b.radius_km.toFixed(0)} km${b.beyond_model_range ? "+" : ""}` : ""}</span>
        </div>
      </div>`
        )
        .join("")
    : `<p class="muted">Kayda değer şiddet beklenen yerleşim yok.</p>`;

  drawImpactMap(d);
  drawSettlementTable(d);

  document.getElementById("i-caveats").innerHTML =
    "<b>Sınırlar:</b><ul>" + d.caveats.map((c) => `<li>${c}</li>`).join("") + "</ul>";
}

function mmiColor(m) {
  return m >= 9 ? "#67000d" : m >= 8 ? "#a50f15" : m >= 7 ? "#ef3b2c"
    : m >= 6 ? "#fd8d3c" : m >= 5 ? "#fecc5c" : m >= 4 ? "#c7e9b4" : "#7fcdbb";
}

function drawImpactMap(d) {
  if (impactLayer) impactMap.removeLayer(impactLayer);
  const layers = [];

  d.bands
    .slice()
    .reverse()
    .forEach((b) => {
      if (!b.radius_km) return;
      layers.push(
        L.circle([d.event.lat, d.event.lon], {
          radius: b.radius_km * 1000,
          color: b.color, weight: 1.5, fillColor: b.color, fillOpacity: 0.12,
          dashArray: b.beyond_model_range ? "6 6" : null,
        }).bindPopup(`<b>MMI ${b.roman}</b> — ${b.label}<br>~${b.radius_km.toFixed(0)} km${b.beyond_model_range ? " (model sınırı)" : ""}<br>${b.settlements} yerleşim`)
      );
    });

  layers.push(
    L.marker([d.event.lat, d.event.lon]).bindPopup(
      `<b>M ${d.event.magnitude.toFixed(1)}</b><br>derinlik ${d.event.depth_km.toFixed(0)} km`
    )
  );

  d.settlements.slice(0, 120).forEach((s) => {
    const c = mmiColor(s.mmi);
    layers.push(
      L.circleMarker([s.lat, s.lon], {
        radius: Math.max(3, Math.log10(Math.max(s.population, 10)) * 1.8),
        color: c, fillColor: c, fillOpacity: 0.85, weight: 0.6,
      }).bindPopup(`<b>${s.name}</b><br>MMI ${s.mmi.toFixed(1)} ± ${s.sigma.toFixed(2)} (${s.roman})<br>${s.population.toLocaleString("tr-TR")} kişi · ${s.distance_km} km`)
    );
  });

  impactLayer = L.layerGroup(layers).addTo(impactMap);
  // Not: haritaya eklenmemiş bir L.circle'da getBounds() çalışmaz (map gerekir);
  // latLng.toBounds() saf geometridir ve haritadan bağımsız hesaplanır.
  const big = d.bands.find((b) => b.radius_km);
  if (big) {
    impactMap.fitBounds(L.latLng(d.event.lat, d.event.lon).toBounds(big.radius_km * 2000));
  }
}

function drawSettlementTable(d) {
  const el = document.getElementById("i-settlements");
  if (!d.settlements.length) {
    el.innerHTML = `<p class="muted">Etkilenen yerleşim yok.</p>`;
    return;
  }
  el.innerHTML = `<table class="forecast-table">
    <tr><th>Yerleşim</th><th>MMI</th><th>Derece</th><th>Uzaklık</th><th>Yaklaşık nüfus</th></tr>
    ${d.settlements.slice(0, 100).map((s) => `<tr>
      <td class="loc-cell" style="color:var(--text)"><b>${s.name}</b></td>
      <td style="color:${mmiColor(s.mmi)};font-weight:700">${s.mmi.toFixed(1)} <span class="muted">±${s.sigma.toFixed(2)}</span></td>
      <td>${s.roman}</td>
      <td>${s.distance_km} km</td>
      <td>${s.population.toLocaleString("tr-TR")}</td>
    </tr>`).join("")}
  </table>`;
}

async function toggleShelters(e) {
  if (!e.target.checked) {
    if (shelterLayer) {
      impactMap.removeLayer(shelterLayer);
      shelterLayer = null;
    }
    return;
  }
  if (!lastImpact) return;
  const p = new URLSearchParams({
    lat: lastImpact.event.lat,
    lon: lastImpact.event.lon,
    radius_km: 120,
  });
  const r = await fetch(`/api/shelters?${p}`);
  if (!r.ok) return;
  const fc = await r.json();
  shelterLayer = L.geoJSON(fc, {
    pointToLayer: (f, latlng) =>
      L.circleMarker(latlng, {
        radius: 4, color: "#2ecc71", fillColor: "#2ecc71", fillOpacity: 0.9, weight: 1,
      }).bindPopup(`<b>Toplanma alanı</b><br>${f.properties.name || "(isimsiz)"}<br>${f.properties.distance_km} km<br><small>OSM — liste eksiktir</small>`),
  }).addTo(impactMap);
  document.getElementById("i-shelter-note").textContent = fc.features.length
    ? `${fc.features.length} toplanma alanı (OSM, eksik veri)`
    : "Bu bölgede OSM'de kayıtlı toplanma alanı yok — resmî liste için AFAD.";
}

/* ══════════ DOĞRULAMA ══════════ */
let validationInited = false;

async function initValidation() {
  if (validationInited) return;
  validationInited = true;
  await Promise.all([loadIntensityValidation(), loadAftershockValidation()]);
}

async function loadIntensityValidation() {
  const r = await fetch("/api/validation/intensity");
  if (!r.ok) {
    document.getElementById("v-int-kpis").innerHTML = kpi("Şiddet doğrulaması", "veri yok");
    return;
  }
  const d = await r.json();
  const o = d.overall;
  const sign = (x) => (x > 0 ? "+" : "");

  document.getElementById("v-int-kpis").innerHTML =
    kpi("Gözlem", o.observations.toLocaleString("tr-TR")) +
    kpi("Olay", o.events.toLocaleString("tr-TR")) +
    kpi("Ortalama sapma", `${sign(o.bias)}${o.bias.toFixed(2)} MMI`) +
    kpi("Ortalama mutlak hata", `${o.mae.toFixed(2)} MMI`) +
    kpi("±1 MMI içinde", `%${(o.within_1_mmi * 100).toFixed(0)}`);

  const gridColor = "rgba(127,140,163,0.15)";
  const mk = (id, cfg) => {
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart(document.getElementById(id), cfg);
  };

  // Gözlenen vs tahmin saçılımı + birebir doğru
  mk("chart-vscatter", {
    type: "scatter",
    data: {
      datasets: [
        {
          label: "DYFI kutuları",
          data: d.scatter.map((s) => ({ x: s.predicted, y: s.observed })),
          backgroundColor: "rgba(52,152,219,0.45)",
          pointRadius: 2.5,
        },
        {
          label: "birebir (mükemmel tahmin)",
          data: [{ x: 2, y: 2 }, { x: 10, y: 10 }],
          type: "line",
          borderColor: "#e74c3c",
          borderDash: [6, 4],
          pointRadius: 0,
          borderWidth: 2,
        },
      ],
    },
    options: {
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: "#e6ecf5", boxWidth: 12 } },
        title: { display: true, text: "Gözlenen vs Tahmin Edilen Şiddet", color: "#e6ecf5" },
      },
      scales: {
        x: { title: { display: true, text: "Tahmin (MMI)", color: "#7f8ca3" }, ticks: { color: "#7f8ca3" }, grid: { color: gridColor }, min: 2, max: 10 },
        y: { title: { display: true, text: "Gözlenen (MMI)", color: "#7f8ca3" }, ticks: { color: "#7f8ca3" }, grid: { color: gridColor }, min: 2, max: 10 },
      },
    },
  });

  // Mesafeye göre sapma
  mk("chart-vresid", {
    type: "bar",
    data: {
      labels: d.by_distance.map((b) => `${b.range} km`),
      datasets: [{
        label: "Ortalama sapma (MMI)",
        data: d.by_distance.map((b) => b.bias),
        backgroundColor: d.by_distance.map((b) => (b.bias > 0 ? "#3498db99" : "#e74c3c99")),
      }],
    },
    options: {
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        title: { display: true, text: "Sapma — Uzaklığa Göre (0 = mükemmel)", color: "#e6ecf5" },
      },
      scales: {
        x: { ticks: { color: "#7f8ca3" }, grid: { color: gridColor } },
        y: { ticks: { color: "#7f8ca3" }, grid: { color: gridColor } },
      },
    },
  });

  const rows = (arr) => arr.map((b) => `<tr>
      <td>${b.group}</td><td><b>${b.range}</b></td><td>${b.n}</td>
      <td class="${Math.abs(b.bias) >= 0.3 ? "prob-mid" : "prob-low"}">${sign(b.bias)}${b.bias.toFixed(2)}</td>
      <td>${b.mae.toFixed(2)}</td><td>${b.rmse.toFixed(2)}</td>
    </tr>`).join("");

  document.getElementById("v-int-bins").innerHTML = `<table class="forecast-table">
    <tr><th>Grup</th><th>Aralık</th><th>Gözlem</th><th>Sapma</th><th>MAE</th><th>RMSE</th></tr>
    ${rows(d.by_distance)}${rows(d.by_magnitude)}
  </table>
  <p class="muted" style="margin-top:8px">Negatif sapma modelin şiddeti FAZLA tahmin ettiğini gösterir.
  Ölçüm, büyük depremlerde (M≥6,5) modelin fazla tahmin ettiğini ortaya koyuyor.</p>`;

  document.getElementById("v-caveats").innerHTML =
    "<b>Doğrulamanın kendi sınırları:</b><ul>" +
    d.caveats.map((c) => `<li>${c}</li>`).join("") + "</ul>";
}

async function loadAftershockValidation() {
  const r = await fetch("/api/validation/aftershock");
  if (!r.ok) return;
  const d = await r.json();

  document.getElementById("v-aft-kpis").innerHTML =
    kpi("Test edilen dizi", `${d.tested} / ${d.candidates}`) +
    kpi("N-testini geçen", d.tested ? `${d.passed} (%${(d.pass_rate * 100).toFixed(0)})` : "—") +
    kpi("Toplam beklenen", d.total_expected != null ? d.total_expected.toFixed(0) : "—") +
    kpi("Toplam gözlenen", d.total_observed != null ? d.total_observed : "—") +
    kpi("Gözlenen / beklenen", d.ratio_observed_expected != null ? d.ratio_observed_expected.toFixed(2) : "—");

  const el = document.getElementById("v-aft-table");
  if (!d.sequences.length) {
    el.innerHTML = `<p class="muted">Yeterli veriye sahip dizi bulunamadı.</p>`;
    return;
  }
  el.innerHTML = `<table class="forecast-table">
    <tr><th>Ana şok</th><th>M</th><th>Mc</th><th>b</th><th>p</th><th>Beklenen</th><th>Gözlenen</th><th>Sonuç</th></tr>
    ${d.sequences.map((s) => `<tr>
      <td>${s.time.slice(0, 10)}<br><span class="muted">${(s.location || "").slice(0, 26)}</span></td>
      <td><b>${s.magnitude.toFixed(1)}</b></td>
      <td>${s.mc.toFixed(1)}</td><td>${s.b.toFixed(2)}</td><td>${s.p.toFixed(2)}</td>
      <td>${s.expected.toFixed(1)}</td><td><b>${s.observed}</b></td>
      <td class="${s.passed ? "pass-ok" : "prob-high"}">${s.passed ? "✓ geçti" : "✗ kaldı"}</td>
    </tr>`).join("")}
  </table>
  <p class="muted" style="margin-top:8px">${d.skipped_insufficient_data} dizi, öğrenme penceresinde
  yeterli artçı içermediği için test edilemedi (katalog M≥4 eşiğinde).
  Hedef büyüklük her dizinin kendi tamlık eşiği (Mc) alınır.</p>`;
}

/* ── başlat ── */


toggleLiveFaults();
refreshLive();
