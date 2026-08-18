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
    ["live", "archive", "seismo"].forEach((v) =>
      document.getElementById(`view-${v}`).classList.toggle("hidden", v !== view)
    );
    if (view === "archive") initArchive();
    if (view === "seismo") initSeismo();
    setTimeout(() => {
      liveMap.invalidateSize();
      archMap && archMap.invalidateSize();
      bMap && bMap.invalidateSize();
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

/* ── başlat ── */
toggleLiveFaults();
refreshLive();
