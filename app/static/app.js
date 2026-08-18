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
    document.getElementById("view-live").classList.toggle("hidden", view !== "live");
    document.getElementById("view-archive").classList.toggle("hidden", view !== "archive");
    if (view === "archive") initArchive();
    setTimeout(() => { liveMap.invalidateSize(); archMap && archMap.invalidateSize(); }, 60);
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

/* ── başlat ── */
toggleLiveFaults();
refreshLive();
