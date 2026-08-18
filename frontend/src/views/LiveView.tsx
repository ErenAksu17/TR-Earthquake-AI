import { useCallback, useEffect, useRef, useState } from "react"
import L from "leaflet"
import { Activity, Gauge, RefreshCw, Timer, Waves } from "lucide-react"
import { api, type Quake } from "@/lib/api"
import { fmtTime, magColor, fmtNum } from "@/lib/seismic"
import { loadFaults, faultStyle, useLeafletMap } from "@/hooks/useLeafletMap"
import { StatCard, StatGrid } from "@/components/StatCard"
import { Toolbar, Field } from "@/components/Toolbar"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"

const REFRESH_S = 60

const SOURCE_LABELS: Record<string, string> = {
  all: "Kandilli + AFAD", kandilli: "Kandilli", afad: "AFAD",
}
const MAG_LABELS: Record<string, string> = {
  "0": "Tümü", "2": "M 2+", "3": "M 3+", "4": "M 4+",
}
/** Base UI Select ham değeri gösterir; etiketi biz eşleriz. */
const labelOf = (map: Record<string, string>) => (v: unknown) =>
  map[String(v)] ?? String(v ?? "")

export function LiveView({ onStatus }: { onStatus: (ok: boolean) => void }) {
  const [source, setSource] = useState("all")
  const [minMag, setMinMag] = useState("0")
  const [showFaults, setShowFaults] = useState(true)
  const [quakes, setQuakes] = useState<Quake[] | null>(null)
  const [updated, setUpdated] = useState<Date | null>(null)
  const [countdown, setCountdown] = useState(REFRESH_S)

  const { ref, map } = useLeafletMap([39, 35], 6)
  const markers = useRef<L.LayerGroup | null>(null)
  const faults = useRef<L.GeoJSON | null>(null)

  const refresh = useCallback(async () => {
    setCountdown(REFRESH_S)
    try {
      const d = await api.live(source, Number(minMag))
      setQuakes(d.quakes)
      setUpdated(new Date())
      onStatus(true)
    } catch {
      onStatus(false)
    }
  }, [source, minMag, onStatus])

  useEffect(() => { refresh() }, [refresh])

  useEffect(() => {
    const id = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) { refresh(); return REFRESH_S }
        return c - 1
      })
    }, 1000)
    return () => clearInterval(id)
  }, [refresh])

  // Fay katmanı
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

  // İşaretçiler
  useEffect(() => {
    const m = map.current
    if (!m || !quakes) return
    markers.current?.remove()
    markers.current = L.layerGroup(
      quakes.map((q) =>
        L.circleMarker([q.latitude, q.longitude], {
          radius: Math.max(5, q.magnitude * 2.6),
          color: magColor(q.magnitude),
          fillColor: magColor(q.magnitude),
          fillOpacity: 0.75,
          weight: 1.2,
        }).bindPopup(
          `<b>${q.location ?? ""}</b><br>${fmtTime(q.eventDate)}<br>` +
          `<b>M ${q.magnitude.toFixed(1)}</b> — ${Math.round(q.depth ?? 0)} km` +
          (q.provider ? `<br><small>Kaynak: ${q.provider}</small>` : "")
        )
      )
    ).addTo(m)
  }, [quakes, map])

  const mags = quakes?.map((q) => q.magnitude) ?? []
  const focus = (q: Quake) => map.current?.setView([q.latitude, q.longitude], 9)

  return (
    <div className="flex flex-col gap-4">
      <Toolbar>
        <Field label="Kaynak">
          <Select value={source} onValueChange={(v) => setSource(v ?? "all")}>
            <SelectTrigger className="w-[190px]">
              <SelectValue>{labelOf(SOURCE_LABELS)}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Kandilli + AFAD</SelectItem>
              <SelectItem value="kandilli">Kandilli</SelectItem>
              <SelectItem value="afad">AFAD</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <Field label="Min. büyüklük">
          <Select value={minMag} onValueChange={(v) => setMinMag(v ?? "0")}>
            <SelectTrigger className="w-[130px]">
              <SelectValue>{labelOf(MAG_LABELS)}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="0">Tümü</SelectItem>
              <SelectItem value="2">M 2+</SelectItem>
              <SelectItem value="3">M 3+</SelectItem>
              <SelectItem value="4">M 4+</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <label className="flex cursor-pointer items-center gap-2 pb-1.5 text-[13px]">
          <Checkbox checked={showFaults} onCheckedChange={(v) => setShowFaults(Boolean(v))} />
          Diri fay hatları
        </label>
        <Button onClick={refresh} variant="secondary" className="gap-2">
          <RefreshCw className="size-3.5" /> Yenile
        </Button>
        <span className="pb-2 text-[11.5px] text-muted-foreground">
          {countdown} sn sonra otomatik yenilenir
        </span>
      </Toolbar>

      <StatGrid>
        <StatCard label="Son 24 saat" value={quakes ? `${quakes.length} deprem` : "—"}
          icon={Activity} tone="critical" />
        <StatCard label="En büyük" value={mags.length ? `M ${Math.max(...mags).toFixed(1)}` : "—"}
          icon={Waves} tone="warm" />
        <StatCard label="Ortalama"
          value={mags.length ? `M ${(mags.reduce((a, b) => a + b, 0) / mags.length).toFixed(2)}` : "—"}
          icon={Gauge} tone="cool" />
        <StatCard label="Son güncelleme"
          value={updated ? updated.toLocaleTimeString("tr-TR", { hour12: false }) : "—"}
          icon={Timer} tone="success" />
      </StatGrid>

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <Card className="glass-panel overflow-hidden p-0">
          <div ref={ref} className="h-[480px] w-full" />
        </Card>

        <Card className="glass-panel flex flex-col">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center justify-between text-sm">
              Son Depremler
              <Badge variant="secondary" className="tabular-nums">{quakes?.length ?? 0}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="flex-1 p-0">
            <ScrollArea className="h-[420px] px-4">
              <div className="flex flex-col gap-1.5 pb-4">
                {!quakes && Array.from({ length: 8 }).map((_, i) =>
                  <Skeleton key={i} className="h-[52px] w-full rounded-lg" />)}
                {quakes?.map((q, i) => (
                  <button key={i} onClick={() => focus(q)}
                    className="hover-lift flex items-center gap-3 rounded-lg border border-transparent bg-secondary/45 px-3 py-2 text-left">
                    <span className="grid min-w-[46px] place-items-center rounded-md px-1.5 py-1 text-[12.5px] font-bold text-white"
                      style={{ background: magColor(q.magnitude) }}>
                      {q.magnitude.toFixed(1)}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[12.5px] font-semibold">
                        {q.location ?? "—"}
                      </span>
                      <span className="block truncate text-[10.5px] text-muted-foreground">
                        {fmtTime(q.eventDate)} · {Math.round(q.depth ?? 0)} km
                        {q.provider ? ` · ${q.provider}` : ""}
                      </span>
                    </span>
                  </button>
                ))}
                {quakes?.length === 0 && (
                  <p className="py-6 text-center text-[13px] text-muted-foreground">
                    Bu filtrede deprem yok.
                  </p>
                )}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      </div>
      <p className="text-[11px] text-muted-foreground">
        Toplam {fmtNum(quakes?.length ?? 0)} kayıt · zamanlar Türkiye saatiyle (UTC+3) gösterilir.
      </p>
    </div>
  )
}
