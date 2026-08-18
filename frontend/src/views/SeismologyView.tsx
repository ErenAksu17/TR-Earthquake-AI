import type { ChartData } from "chart.js"
import { useCallback, useEffect, useRef, useState } from "react"
import L from "leaflet"
import { Scatter } from "react-chartjs-2"
import { Activity, Grid3x3, Sigma, Waves } from "lucide-react"
import { api, type AftershockResponse, type GRResponse, type Quake } from "@/lib/api"
import { baseChartOptions, fmtNum } from "@/lib/seismic"
import { loadFaults, faultStyle, useLeafletMap } from "@/hooks/useLeafletMap"
import { StatCard, StatGrid } from "@/components/StatCard"
import { Toolbar, Field } from "@/components/Toolbar"
import { InfoNote } from "@/components/InfoNote"
import { SectionTitle } from "@/components/SectionTitle"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"

const bColor = (b: number) =>
  b < 0.75 ? "#dc2626" : b < 0.9 ? "#f97316" : b < 1.05 ? "#fbbf24" : b < 1.2 ? "#84cc16" : "#38bdf8"

export function SeismologyView() {
  const [start, setStart] = useState("1990-01-01")
  const [end, setEnd] = useState(new Date().toISOString().slice(0, 10))
  const [declustered, setDeclustered] = useState(false)
  const [gr, setGr] = useState<GRResponse | null>(null)
  const [decl, setDecl] = useState<{ total: number; aftershock_pct: number } | null>(null)
  const [mains, setMains] = useState<Quake[]>([])
  const [selected, setSelected] = useState<string>("")
  const [forecast, setForecast] = useState<AftershockResponse | null>(null)

  const { ref, map } = useLeafletMap([39, 35], 5)
  const cells = useRef<L.LayerGroup | null>(null)

  const compute = useCallback(async () => {
    try {
      setGr(await api.gr({ start, end, declustered }))
    } catch { setGr(null) }
  }, [start, end, declustered])

  useEffect(() => { compute() }, [compute])

  useEffect(() => {
    api.decluster().then(setDecl).catch(() => {})
    api.mainshocks(5.5, 30).then((d) => {
      setMains(d.mainshocks)
      if (d.mainshocks.length) setSelected("0")
    }).catch(() => {})
  }, [])

  // b-değeri haritası + fay katmanı
  useEffect(() => {
    if (!map.current) return
    let cancelled = false
    ;(async () => {
      const gj = await loadFaults()
      if (gj && !cancelled && map.current) {
        L.geoJSON(gj, { style: { ...faultStyle, opacity: 0.25 } }).addTo(map.current)
      }
      const d = await api.bmap(1.0).catch(() => null)
      if (!d || cancelled || !map.current) return
      cells.current?.remove()
      cells.current = L.layerGroup(
        d.cells.map((c) => {
          const h = c.cell_deg / 2
          return L.rectangle([[c.lat - h, c.lon - h], [c.lat + h, c.lon + h]], {
            color: bColor(c.b), weight: 0.6, fillColor: bColor(c.b), fillOpacity: 0.42,
          }).bindPopup(
            `<b>b = ${c.b} ± ${c.b_err}</b><br>Mc = M ${c.mc.toFixed(1)}<br>${c.n} deprem (M ≥ Mc)`
          )
        })
      ).addTo(map.current)
    })()
    return () => { cancelled = true }
  }, [map])

  const runForecast = async () => {
    const m = mains[Number(selected)]
    if (!m) return
    try {
      setForecast(await api.aftershock({
        time: m.eventDate, lat: m.latitude, lon: m.longitude, mag: m.magnitude,
      }))
    } catch { setForecast(null) }
  }

  useEffect(() => { if (mains.length && selected) runForecast() // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, mains])

  const probTone = (p: number) => p >= 0.5 ? "text-rose-400" : p >= 0.1 ? "text-amber-400" : "text-muted-foreground"

  return (
    <div className="flex flex-col gap-4">
      <InfoNote title="Bu sayfa ne yapar, ne yapmaz?">
        Burada operasyonel sismolojinin kullandığı <b>istatistiksel</b> yöntemler var:
        Gutenberg-Richter büyüklük-frekans ilişkisi (b-değeri), Gardner-Knopoff katalog
        ayıklama ve Omori-Utsu artçı şok bozunumu. Bunların hepsi <b>olasılıksal</b>
        araçlardır — hiçbiri "şu tarihte şurada deprem olacak" diyemez; deterministik
        kısa vadeli deprem tahmini bilimsel olarak mümkün değildir.
      </InfoNote>

      <Toolbar>
        <Field label="Başlangıç">
          <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="w-[150px]" />
        </Field>
        <Field label="Bitiş">
          <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="w-[150px]" />
        </Field>
        <label className="flex cursor-pointer items-center gap-2 pb-1.5 text-[13px]">
          <Checkbox checked={declustered} onCheckedChange={(v) => setDeclustered(Boolean(v))} />
          Artçılar ayıklansın (Gardner-Knopoff)
        </label>
        <Button onClick={compute}>Hesapla</Button>
        {decl && (
          <span className="pb-2 text-[11.5px] text-muted-foreground">
            Katalog: {fmtNum(decl.total)} kayıt — %{decl.aftershock_pct} artçı
          </span>
        )}
      </Toolbar>

      <StatGrid className="lg:grid-cols-5">
        <StatCard label="b-değeri" value={gr?.fit ? `${gr.fit.b} ± ${gr.fit.b_err}` : "—"} icon={Sigma} tone="critical" />
        <StatCard label="Mc (tamlık eşiği)" value={gr?.mc != null ? `M ${gr.mc.toFixed(1)}` : "—"} icon={Activity} tone="warm" />
        <StatCard label="a-değeri" value={gr?.fit ? gr.fit.a : "—"} icon={Sigma} tone="cool" />
        <StatCard label="Kayıt (M ≥ Mc)" value={gr?.fit ? fmtNum(gr.fit.n) : "—"} icon={Grid3x3} tone="success" />
        <StatCard label="Toplam kayıt" value={gr ? fmtNum(gr.n_total) : "—"} icon={Grid3x3} />
      </StatGrid>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="glass-panel">
          <CardHeader className="pb-1">
            <CardTitle className="text-sm">Gutenberg-Richter Büyüklük-Frekans İlişkisi</CardTitle>
          </CardHeader>
          <CardContent className="h-[300px]">
            {gr && (
              <Scatter
                data={{
                  datasets: [
                    { label: "Gözlenen N(≥M)",
                      data: gr.curve.mags.map((m, i) => ({ x: m, y: gr.curve.counts[i] })),
                      backgroundColor: "#38bdf8", pointRadius: 3 },
                    ...(gr.curve.fit ? [{
                      label: `G-R uyumu (b=${gr.fit?.b})`,
                      data: gr.curve.fit.map((f) => ({ x: f.m, y: f.n })),
                      type: "line" as const, borderColor: "#f43f5e", pointRadius: 0, borderWidth: 2,
                    }] : []),
                  ],
                } as unknown as ChartData<"scatter">}
                options={{
                  ...baseChartOptions(),
                  scales: {
                    x: { ...baseChartOptions().scales.x, title: { display: true, text: "Büyüklük (M)", color: "#94a3b8" } },
                    y: { type: "logarithmic" as const, ticks: { color: "#94a3b8", font: { size: 10 } },
                         grid: { color: "rgba(148,163,184,0.13)" },
                         title: { display: true, text: "N (≥M) — log", color: "#94a3b8" } },
                  },
                }}
              />
            )}
          </CardContent>
        </Card>

        <Card className="glass-panel">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Bölgesel b-değeri Haritası</CardTitle>
            <p className="text-[11px] text-muted-foreground">Düşük b = büyük deprem payı yüksek</p>
          </CardHeader>
          <CardContent className="p-3 pt-0">
            <div ref={ref} className="h-[260px] w-full overflow-hidden rounded-lg" />
          </CardContent>
        </Card>
      </div>

      <SectionTitle icon={Waves} title="Artçı Şok Tahmini"
        subtitle="Omori-Utsu bozunumu + Reasenberg-Jones olasılığı" />

      <Card className="glass-panel">
        <CardContent className="flex flex-col gap-4 pt-5">
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Ana şok seç">
              <Select value={selected} onValueChange={(v) => setSelected(v ?? "")}>
                <SelectTrigger className="w-[380px]">
                  <SelectValue placeholder="Seçin">
                    {(v: unknown) => {
                      const m = mains[Number(v)]
                      return m
                        ? `M ${m.magnitude.toFixed(1)} — ${(m.location ?? "?").slice(0, 30)}`
                        : "Seçin"
                    }}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {mains.map((m, i) => (
                    <SelectItem key={i} value={String(i)}>
                      M {m.magnitude.toFixed(1)} — {(m.location ?? "?").slice(0, 34)} ({m.eventDate.slice(0, 10)})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Button onClick={runForecast}>Tahmin Et</Button>
          </div>

          {forecast && (
            <>
              <div className="flex flex-wrap gap-2 text-[11.5px] text-muted-foreground">
                <Badge variant="secondary">{fmtNum(forecast.sequence_events)} kayıt</Badge>
                <Badge variant="secondary">geçen süre {Math.round(forecast.elapsed_days)} gün</Badge>
                <Badge variant="secondary">b = {forecast.b_value}</Badge>
                {forecast.omori && <Badge variant="secondary">p = {forecast.omori.p} · c = {forecast.omori.c}</Badge>}
              </div>

              {forecast.forecast ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Ufuk</TableHead>
                      {[...new Set(forecast.forecast.map((f) => f.min_mag))].map((m) => (
                        <TableHead key={m} className="text-center">M ≥ {m.toFixed(0)}</TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {[...new Set(forecast.forecast.map((f) => f.horizon_days))].map((h) => (
                      <TableRow key={h}>
                        <TableCell className="font-medium">Önümüzdeki {h} gün</TableCell>
                        {[...new Set(forecast.forecast!.map((f) => f.min_mag))].map((m) => {
                          const f = forecast.forecast!.find((x) => x.horizon_days === h && x.min_mag === m)!
                          return (
                            <TableCell key={m} className="text-center">
                              <span className={`font-bold ${probTone(f.probability)}`}>
                                %{(f.probability * 100).toFixed(1)}
                              </span>
                              <span className="block text-[10.5px] text-muted-foreground">
                                ~{f.expected.toFixed(2)} adet
                              </span>
                            </TableCell>
                          )
                        })}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <p className="text-[13px] text-muted-foreground">
                  {forecast.note ?? "Bu dizi için tahmin üretilemedi."}
                </p>
              )}
              <p className="text-[11px] text-muted-foreground">
                En az bir M≥m artçı olma olasılığı. Dizi eskidikçe olasılıklar düşer — bu beklenen davranıştır.
              </p>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
