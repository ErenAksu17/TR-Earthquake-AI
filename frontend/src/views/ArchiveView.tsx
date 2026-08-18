import type { ChartData } from "chart.js"
import { useCallback, useEffect, useRef, useState } from "react"
import L from "leaflet"
import "leaflet.heat"
import { Bar } from "react-chartjs-2"
import { CalendarRange, Database, Download, Layers, Ruler, TrendingUp } from "lucide-react"
import { api, type QuakesResponse, type StatsResponse } from "@/lib/api"
import { baseChartOptions, fmtNum, magColor, fmtTime } from "@/lib/seismic"
import { loadFaults, faultStyle, useLeafletMap } from "@/hooks/useLeafletMap"
import { StatCard, StatGrid } from "@/components/StatCard"
import { Toolbar, Field } from "@/components/Toolbar"
import { Button, buttonVariants } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

const today = () => new Date().toISOString().slice(0, 10)

const MODE_LABELS: Record<string, string> = { markers: "İşaretçiler", heat: "Isı haritası" }

export function ArchiveView() {
  const [start, setStart] = useState("1900-01-01")
  const [end, setEnd] = useState(today())
  const [minMag, setMinMag] = useState("4.0")
  const [maxMag, setMaxMag] = useState("10")
  const [minDepth, setMinDepth] = useState("0")
  const [maxDepth, setMaxDepth] = useState("700")
  const [q, setQ] = useState("")
  const [mode, setMode] = useState("markers")
  const [showFaults, setShowFaults] = useState(true)

  const [data, setData] = useState<QuakesResponse | null>(null)
  const [stats, setStats] = useState<StatsResponse | null>(null)

  const { ref, map } = useLeafletMap([39, 35], 6)
  const layer = useRef<L.Layer | null>(null)
  const faults = useRef<L.GeoJSON | null>(null)

  const filters = {
    start, end, min_mag: minMag, max_mag: maxMag,
    min_depth: minDepth, max_depth: maxDepth, q,
  }

  const apply = useCallback(async () => {
    const [d, s] = await Promise.all([
      api.quakes({ ...filters, limit: 5000 }),
      api.stats(filters),
    ])
    setData(d)
    setStats(s)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [start, end, minMag, maxMag, minDepth, maxDepth, q])

  useEffect(() => { apply() }, [apply])

  useEffect(() => {
    if (!map.current) return
    let cancelled = false
    ;(async () => {
      const m = map.current
      if (!m) return
      if (showFaults) {
        if (!faults.current) {
          const gj = await loadFaults()
          if (!gj || cancelled || !map.current) return
          faults.current = L.geoJSON(gj, { style: faultStyle })
        }
        faults.current.addTo(m)
      } else if (faults.current) {
        m.removeLayer(faults.current)
      }
    })()
    return () => { cancelled = true }
  }, [showFaults, map])

  useEffect(() => {
    if (!map.current || !data) return
    if (layer.current) map.current.removeLayer(layer.current)
    if (mode === "heat") {
      layer.current = (L as unknown as {
        heatLayer: (pts: [number, number, number][], o: object) => L.Layer
      }).heatLayer(
        data.quakes.map((x) => [x.latitude, x.longitude, Math.pow(10, x.magnitude - 4)] as [number, number, number]),
        { radius: 13, blur: 20, gradient: { 0.2: "#38bdf8", 0.5: "#22d3ee", 0.7: "#fbbf24", 1.0: "#f43f5e" } }
      )
    } else {
      layer.current = L.layerGroup(
        data.quakes.map((x) =>
          L.circleMarker([x.latitude, x.longitude], {
            radius: Math.max(3, (x.magnitude - 3) * 2.2),
            color: magColor(x.magnitude), fillColor: magColor(x.magnitude),
            fillOpacity: 0.55, weight: 0.5,
          }).bindPopup(
            `<b>${x.location ?? ""}</b><br>${fmtTime(x.eventDate, false)}<br><b>M ${x.magnitude.toFixed(1)}</b> — ${Math.round(x.depth ?? 0)} km`
          )
        )
      )
    }
    layer.current.addTo(map.current)
  }, [data, mode, map])

  return (
    <div className="flex flex-col gap-4">
      <Toolbar>
        <Field label="Başlangıç">
          <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="w-[150px]" />
        </Field>
        <Field label="Bitiş">
          <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="w-[150px]" />
        </Field>
        <Field label="Büyüklük">
          <div className="flex items-center gap-1.5">
            <Input type="number" step="0.1" value={minMag} onChange={(e) => setMinMag(e.target.value)} className="w-[74px]" />
            <span className="text-muted-foreground">–</span>
            <Input type="number" step="0.1" value={maxMag} onChange={(e) => setMaxMag(e.target.value)} className="w-[74px]" />
          </div>
        </Field>
        <Field label="Derinlik (km)">
          <div className="flex items-center gap-1.5">
            <Input type="number" value={minDepth} onChange={(e) => setMinDepth(e.target.value)} className="w-[74px]" />
            <span className="text-muted-foreground">–</span>
            <Input type="number" value={maxDepth} onChange={(e) => setMaxDepth(e.target.value)} className="w-[74px]" />
          </div>
        </Field>
        <Field label="Konum">
          <Input placeholder="İstanbul, Ege…" value={q} onChange={(e) => setQ(e.target.value)} className="w-[170px]" />
        </Field>
        <Button onClick={apply} className="gap-2">Uygula</Button>
        <a href={api.csvUrl(filters)} download
           className={cn(buttonVariants({ variant: "secondary" }), "gap-2")}>
          <Download className="size-3.5" /> CSV
        </a>
      </Toolbar>

      <StatGrid className="lg:grid-cols-5">
        <StatCard label="Toplam kayıt" value={stats?.total ? fmtNum(stats.total) : "—"} icon={Database} tone="cool" />
        <StatCard label="En büyük" value={stats?.max_mag ? `M ${stats.max_mag.toFixed(1)}` : "—"} icon={TrendingUp} tone="critical" />
        <StatCard label="Ortalama" value={stats?.avg_mag ? `M ${stats.avg_mag}` : "—"} icon={Layers} tone="warm" />
        <StatCard label="Ort. derinlik" value={stats?.avg_depth ? `${stats.avg_depth} km` : "—"} icon={Ruler} tone="success" />
        <StatCard label="Aralık"
          value={stats?.date_min ? `${stats.date_min.slice(0, 4)}–${stats.date_max?.slice(0, 4)}` : "—"}
          icon={CalendarRange} />
      </StatGrid>

      <Toolbar className="py-2">
        <Field label="Görünüm">
          <Select value={mode} onValueChange={(v) => setMode(v ?? "markers")}>
            <SelectTrigger className="w-[160px]">
              <SelectValue>{(v: unknown) => MODE_LABELS[String(v)] ?? String(v ?? "")}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="markers">İşaretçiler</SelectItem>
              <SelectItem value="heat">Isı haritası</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <label className="flex cursor-pointer items-center gap-2 pb-1.5 text-[13px]">
          <Checkbox checked={showFaults} onCheckedChange={(v) => setShowFaults(Boolean(v))} />
          Diri fay hatları
        </label>
        {data && data.total > data.returned && (
          <span className="pb-2 text-[11.5px] text-muted-foreground">
            {fmtNum(data.total)} kayıttan en güncel {fmtNum(data.returned)} tanesi haritada
          </span>
        )}
      </Toolbar>

      <Card className="glass-panel overflow-hidden p-0">
        <div ref={ref} className="h-[520px] w-full" />
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="glass-panel lg:col-span-2">
          <CardHeader className="pb-1"><CardTitle className="text-sm">Yıllık Deprem Sayısı</CardTitle></CardHeader>
          <CardContent className="h-[280px]">
            {stats?.yearly && (
              <Bar
                data={{
                  labels: stats.yearly.years,
                  datasets: [
                    { label: "Deprem sayısı", data: stats.yearly.counts, backgroundColor: "rgba(244,63,94,0.55)", yAxisID: "y" },
                    { label: "En büyük Mw", data: stats.yearly.max_mags, type: "line" as const,
                      borderColor: "#fbbf24", backgroundColor: "#fbbf24", pointRadius: 0, borderWidth: 2, yAxisID: "y2" },
                  ],
                } as unknown as ChartData<"bar">}
                options={{
                  ...baseChartOptions(),
                  scales: {
                    ...baseChartOptions().scales,
                    y2: { position: "right" as const, min: 4, max: 9,
                      ticks: { color: "#fbbf24", font: { size: 10 } }, grid: { display: false } },
                  },
                }}
              />
            )}
          </CardContent>
        </Card>

        <Card className="glass-panel">
          <CardHeader className="pb-1"><CardTitle className="text-sm">Büyüklük Dağılımı</CardTitle></CardHeader>
          <CardContent className="h-[260px]">
            {stats?.mag_hist && (
              <Bar data={{ labels: stats.mag_hist.labels,
                datasets: [{ label: "Adet", data: stats.mag_hist.counts, backgroundColor: "rgba(251,146,60,0.6)" }] }}
                options={{ ...baseChartOptions(), plugins: { ...baseChartOptions().plugins, legend: { display: false } } }} />
            )}
          </CardContent>
        </Card>

        <Card className="glass-panel">
          <CardHeader className="pb-1"><CardTitle className="text-sm">Derinlik Dağılımı</CardTitle></CardHeader>
          <CardContent className="h-[260px]">
            {stats?.depth_hist && (
              <Bar data={{ labels: stats.depth_hist.labels,
                datasets: [{ label: "Adet", data: stats.depth_hist.counts, backgroundColor: "rgba(56,189,248,0.6)" }] }}
                options={{ ...baseChartOptions(), plugins: { ...baseChartOptions().plugins, legend: { display: false } } }} />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
