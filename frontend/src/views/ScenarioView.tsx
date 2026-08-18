import { useCallback, useEffect, useRef, useState } from "react"
import L from "leaflet"
import { AlertTriangle, Layers, Mountain, Percent, Ruler, Users, Zap } from "lucide-react"
import { api, type FaultSource, type ScenarioResponse } from "@/lib/api"
import { fmtMillions, fmtNum, mmiColor } from "@/lib/seismic"
import { useLeafletMap } from "@/hooks/useLeafletMap"
import { StatCard, StatGrid } from "@/components/StatCard"
import { Toolbar, Field } from "@/components/Toolbar"
import { InfoNote, CaveatList } from "@/components/InfoNote"
import { SectionTitle } from "@/components/SectionTitle"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"

/** NEHRP zemin sınıfı rengi — yumuşak zemin sıcak renkte. */
const nehrpColor = (c: string) =>
  c === "E" ? "#b91c1c" : c === "D" ? "#f97316" : c === "C" ? "#fbbf24" : "#38bdf8"

const faultColor = (p50: number | null) =>
  p50 == null ? "#64748b" : p50 >= 0.3 ? "#f43f5e" : p50 >= 0.1 ? "#fb923c" : p50 >= 0.03 ? "#fbbf24" : "#64748b"

export function ScenarioView() {
  const [faults, setFaults] = useState<FaultSource[]>([])
  const [selected, setSelected] = useState<string>("")
  const [fraction, setFraction] = useState(100)
  const [data, setData] = useState<ScenarioResponse | null>(null)
  const [loading, setLoading] = useState(false)

  const { ref, map } = useLeafletMap([39.2, 33], 6)
  const faultLayer = useRef<L.GeoJSON | null>(null)
  const resultLayer = useRef<L.LayerGroup | null>(null)

  // Fay listesi + harita katmanı
  useEffect(() => {
    api.faultSources(400).then((d) => {
      setFaults(d.faults)
      if (d.faults.length) setSelected(d.faults[0].fault_id)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!map.current) return
    let cancelled = false
    ;(async () => {
      const gj = await api.faultGeometry().catch(() => null)
      if (!gj || cancelled || !map.current) return
      faultLayer.current = L.geoJSON(gj, {
        style: (f) => ({
          color: faultColor((f?.properties as { p50?: number })?.p50 ?? null),
          weight: 2, opacity: 0.75,
        }),
        onEachFeature: (f, layer) => {
          const p = f.properties as Record<string, unknown>
          layer.bindPopup(
            `<b>${p.label}</b><br>M<sub>maks</sub> ${Number(p.mmax).toFixed(1)} · ${p.slip_type}<br>` +
            `Yinelenme ~${p.recurrence_years ?? "?"} yıl<br>50 yılda %${((Number(p.p50) || 0) * 100).toFixed(0)}`
          )
          layer.on("click", () => setSelected(String(p.fault_id)))
        },
      }).addTo(map.current)
    })()
    return () => { cancelled = true }
  }, [map])

  const run = useCallback(async () => {
    if (!selected) return
    setLoading(true)
    try {
      setData(await api.scenario({ fault_id: selected, rupture_fraction: fraction / 100 }))
    } catch { setData(null) } finally { setLoading(false) }
  }, [selected, fraction])

  useEffect(() => { run() }, [run])

  // Senaryo sonucunu haritaya çiz
  useEffect(() => {
    if (!map.current || !data || !data.rupture.geometry.length) return
    resultLayer.current?.remove()
    const layers: L.Layer[] = []

    // Kırılan fay bölümü — kalın ve parlak
    layers.push(L.polyline(data.rupture.geometry as [number, number][], {
      color: "#fff", weight: 6, opacity: 0.9,
    }))
    layers.push(L.polyline(data.rupture.geometry as [number, number][], {
      color: "#f43f5e", weight: 3, opacity: 1,
    }).bindPopup(`<b>Kırılma yüzeyi</b><br>${data.rupture.length_km} km → M ${data.rupture.magnitude}`))

    data.settlements.slice(0, 150).forEach((s) => {
      const c = mmiColor(s.mmi)
      layers.push(L.circleMarker([s.lat, s.lon], {
        radius: Math.max(3, Math.log10(Math.max(s.population, 10)) * 1.9),
        color: c, fillColor: c, fillOpacity: 0.85, weight: 0.6,
      }).bindPopup(
        `<b>${s.name}</b><br>MMI <b>${s.mmi.toFixed(1)}</b> (${s.roman})<br>` +
        `kaya ${s.mmi_rock.toFixed(1)} · zemin ${s.delta >= 0 ? "+" : ""}${s.delta.toFixed(2)}<br>` +
        `Vs30 ${s.vs30} m/s (sınıf ${s.nehrp})<br>${s.rjb_km} km · ${s.population.toLocaleString("tr-TR")} kişi`
      ))
    })

    resultLayer.current = L.layerGroup(layers).addTo(map.current)
    map.current.fitBounds(L.polyline(data.rupture.geometry as [number, number][]).getBounds().pad(0.6))
  }, [data, map])

  const f = data?.fault
  const se = data?.site_effect

  return (
    <div className="flex flex-col gap-4">
      <InfoNote title="Bu fay kırılırsa ne olur?">
        Her fay için kırılma alanından <b>Wells &amp; Coppersmith (1994)</b> ile maksimum
        büyüklük, kayma hızından <b>moment dengesiyle</b> yinelenme aralığı hesaplanır.
        Sarsıntı, nokta kaynak değil <b>gerçek fay hattına uzaklıkla</b> hesaplanır ve
        her yerleşimin <b>Vs30 zemin değeri</b> ile düzeltilir.
        <br /><br />
        <b>Bu bir tahmin değil, senaryodur.</b> Fayın ne zaman kırılacağını söylemez;
        olasılıklar uzun dönem ortalamalardır. Moment dengesi tüm kaymanın büyük
        depremlerde boşaldığını varsaydığı için yinelenme aralıkları <b>alt sınırdır</b>
        (olasılıklar yüksek taraftan hatalıdır).
      </InfoNote>

      <Toolbar>
        <Field label="Fay seç (50 yıllık olasılığa göre sıralı)">
          <Select value={selected} onValueChange={(v) => setSelected(v ?? "")}>
            <SelectTrigger className="w-[430px]">
              <SelectValue placeholder="Fay seçin">
                {(v: unknown) => {
                  const x = faults.find((q) => q.fault_id === String(v))
                  return x ? `${x.label} — M${x.mmax.toFixed(1)} · 50y %${((x.p50 ?? 0) * 100).toFixed(0)}` : "Fay seçin"
                }}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {faults.slice(0, 200).map((x) => (
                <SelectItem key={x.fault_id} value={x.fault_id}>
                  {x.label} — M{x.mmax.toFixed(1)} · {x.slip_type} · 50y %{((x.p50 ?? 0) * 100).toFixed(0)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field label={`Kırılan bölüm: %${fraction}`}>
          <input type="range" min={10} max={100} step={5} value={fraction}
            onChange={(e) => setFraction(Number(e.target.value))}
            className="h-2 w-[220px] cursor-pointer appearance-none rounded-full bg-secondary accent-primary" />
        </Field>
        <Field label="Büyüklük (hesaplanan)">
          <Input readOnly value={data ? `M ${data.rupture.magnitude}` : "—"} className="w-[110px] font-bold" />
        </Field>
        {loading && <span className="pb-2 text-[11.5px] text-muted-foreground">hesaplanıyor…</span>}
      </Toolbar>

      {!data && <Skeleton className="h-24 w-full rounded-xl" />}

      <StatGrid className="lg:grid-cols-6">
        <StatCard label="Senaryo büyüklüğü" value={data ? `M ${data.rupture.magnitude}` : "—"}
          icon={Zap} tone="critical" hint={data ? `${data.rupture.length_km} km kırık` : undefined} />
        <StatCard label="En yüksek şiddet" value={data?.max_mmi ? `MMI ${data.max_mmi.toFixed(1)}` : "—"}
          icon={AlertTriangle} tone="critical" />
        <StatCard label="Etkilenen nüfus" value={data ? `~${fmtMillions(data.total_population)}` : "—"}
          icon={Users} tone="warm" />
        <StatCard label="Zeminden gelen artış"
          value={se ? `+${se.mean_delta.toFixed(2)} MMI` : "—"}
          icon={Mountain} tone="warm" hint={se ? `en fazla +${se.max_delta.toFixed(2)}` : undefined} />
        <StatCard label="Yinelenme aralığı"
          value={f?.recurrence_years ? `~${fmtNum(f.recurrence_years)} yıl` : "—"}
          icon={Ruler} tone="cool" />
        <StatCard label="50 yıllık olasılık"
          value={f?.p50 != null ? `%${(f.p50 * 100).toFixed(0)}` : "—"}
          icon={Percent} tone="cool" hint="uzun dönem, Poisson" />
      </StatGrid>

      <div className="grid gap-4 lg:grid-cols-[1fr_330px]">
        <Card className="glass-panel overflow-hidden p-0">
          <div ref={ref} className="h-[520px] w-full" />
        </Card>

        <div className="flex flex-col gap-4">
          <Card className="glass-panel">
            <CardHeader className="pb-2"><CardTitle className="text-sm">Fay Bilgisi</CardTitle></CardHeader>
            <CardContent className="space-y-1.5 text-[12.5px]">
              {f ? (
                <>
                  <div className="font-semibold">{f.label}</div>
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    <Badge variant="secondary">{f.slip_type}</Badge>
                    <Badge variant="secondary">{f.model}</Badge>
                    <Badge variant="secondary">M<sub>maks</sub> {f.mmax?.toFixed(1)}</Badge>
                  </div>
                  <div className="pt-2 text-muted-foreground">
                    Uzunluk {f.length_km} km · genişlik {f.width_km} km<br />
                    Kayma hızı {f.slip_rate?.toFixed(1) ?? "?"} mm/yıl
                  </div>
                </>
              ) : <span className="text-muted-foreground">—</span>}
            </CardContent>
          </Card>

          <Card className="glass-panel flex-1">
            <CardHeader className="pb-2"><CardTitle className="text-sm">Şiddet Bantları</CardTitle></CardHeader>
            <CardContent className="px-4">
              {data?.bands.length ? [...data.bands].reverse().map((b) => (
                <div key={b.roman} className="flex items-center gap-3 border-b border-border/60 py-2 last:border-0">
                  <span className="grid min-w-[44px] place-items-center rounded-md px-1.5 py-1 text-[12px] font-bold text-white"
                    style={{ background: b.color }}>{b.roman}</span>
                  <div className="min-w-0">
                    <div className="text-[12.5px] font-semibold">{b.label}</div>
                    <div className="text-[11px] text-muted-foreground">
                      {b.settlements} yerleşim · ~{(b.population / 1e6).toFixed(2)} milyon
                    </div>
                  </div>
                </div>
              )) : <p className="py-4 text-[13px] text-muted-foreground">—</p>}
            </CardContent>
          </Card>
        </div>
      </div>

      <SectionTitle icon={Layers} title="Zemin Etkisi Yerleşim Bazında"
        subtitle="Kaya üzerindeki şiddet ile zemin düzeltmeli şiddet yan yana" />

      <Card className="glass-panel">
        <CardContent className="p-0">
          <ScrollArea className="h-[420px]">
            <Table>
              <TableHeader className="sticky top-0 bg-card/95 backdrop-blur">
                <TableRow>
                  <TableHead>Yerleşim</TableHead>
                  <TableHead className="text-center">Uzaklık</TableHead>
                  <TableHead className="text-center">Kayada MMI</TableHead>
                  <TableHead className="text-center">Zemin katkısı</TableHead>
                  <TableHead className="text-center">Sonuç MMI</TableHead>
                  <TableHead className="text-center">Vs30</TableHead>
                  <TableHead className="text-right">Nüfus</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(data?.settlements ?? []).slice(0, 120).map((s, i) => (
                  <TableRow key={i}>
                    <TableCell className="font-semibold">{s.name}</TableCell>
                    <TableCell className="text-center tabular-nums">{s.rjb_km} km</TableCell>
                    <TableCell className="text-center tabular-nums text-muted-foreground">
                      {s.mmi_rock.toFixed(1)}
                    </TableCell>
                    <TableCell className={`text-center font-bold tabular-nums ${s.delta > 0.3 ? "text-rose-400" : s.delta > 0 ? "text-amber-400" : "text-sky-400"}`}>
                      {s.delta >= 0 ? "+" : ""}{s.delta.toFixed(2)}
                    </TableCell>
                    <TableCell className="text-center font-bold tabular-nums" style={{ color: mmiColor(s.mmi) }}>
                      {s.mmi.toFixed(1)} <span className="text-[10.5px] font-normal text-muted-foreground">{s.roman}</span>
                    </TableCell>
                    <TableCell className="text-center">
                      <span className="rounded px-1.5 py-0.5 text-[11px] font-semibold text-white"
                        style={{ background: nehrpColor(s.nehrp) }}>
                        {s.vs30} · {s.nehrp}
                      </span>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{fmtNum(s.population)}</TableCell>
                  </TableRow>
                ))}
                {!data?.settlements?.length && (
                  <TableRow><TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                    Bu senaryoda kayda değer şiddet beklenen yerleşim yok.
                  </TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </ScrollArea>
        </CardContent>
      </Card>

      <CaveatList items={data?.caveats ?? []} />
    </div>
  )
}
