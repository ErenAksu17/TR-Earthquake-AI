import { useCallback, useEffect, useState } from "react"
import { Bar, Scatter } from "react-chartjs-2"
import { GitCompareArrows, Scale } from "lucide-react"
import { api, type CompareResponse } from "@/lib/api"
import { baseChartOptions, fmtNum, fmtTime } from "@/lib/seismic"
import { StatCard, StatGrid } from "@/components/StatCard"
import { Toolbar, Field } from "@/components/Toolbar"
import { InfoNote } from "@/components/InfoNote"
import { SectionTitle } from "@/components/SectionTitle"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"

export function CompareView() {
  const [start, setStart] = useState("2023-02-01")
  const [end, setEnd] = useState("2023-02-28")
  const [minMag, setMinMag] = useState("4.5")
  const [data, setData] = useState<CompareResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      setData(await api.compare({ start, end, min_mag: minMag, samples: 60 }))
    } catch {
      setError("Kaynaklara erişilemedi.")
    } finally { setLoading(false) }
  }, [start, end, minMag])

  useEffect(() => { run() }, [run])

  const cmp = data?.comparisons?.[0]
  const st = cmp?.stats
  const cat = Object.fromEntries((data?.catalogs ?? []).map((c) => [c.source, c]))
  const pairs = data?.pairs ?? []
  const sign = (x: number) => (x > 0 ? "+" : "")

  // Büyüklük farkı histogramı
  const bins: Record<string, number> = {}
  pairs.forEach((p) => {
    const k = (Math.round(p.dmag * 10) / 10).toFixed(1)
    bins[k] = (bins[k] ?? 0) + 1
  })
  const binLabels = Object.keys(bins).sort((a, b) => Number(a) - Number(b))

  return (
    <div className="flex flex-col gap-4">
      <InfoNote title="Aynı deprem, farklı sayılar">
        Her kurum depremi kendi ağıyla ölçer; büyüklük, episantr ve derinlik değerleri
        farklı çıkar. AFAD <code className="rounded bg-secondary px-1 py-0.5 text-[11px]">ML</code> ve
        <code className="mx-1 rounded bg-secondary px-1 py-0.5 text-[11px]">MW</code>, USGS
        <code className="mx-1 rounded bg-secondary px-1 py-0.5 text-[11px]">mb</code>
        <code className="mr-1 rounded bg-secondary px-1 py-0.5 text-[11px]">mww</code>
        ölçeklerini kullanır — "hangisi doğru?" sorusunun tek cevabı yoktur; ölçtükleri şey farklıdır.
        <br /><br />
        <b>Kapsam sınırı:</b> USGS'in Türkiye'deki fiilî eşiği ~M4.0'dır. Kandilli'nin açık
        API'si tarihsel sorgulamaya izin vermediği için karşılaştırma AFAD ile USGS arasındadır.
      </InfoNote>

      <Toolbar>
        <Field label="Başlangıç">
          <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="w-[150px]" />
        </Field>
        <Field label="Bitiş">
          <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="w-[150px]" />
        </Field>
        <Field label="Min. büyüklük">
          <Input type="number" step="0.1" value={minMag} onChange={(e) => setMinMag(e.target.value)} className="w-[90px]" />
        </Field>
        <Button onClick={run} disabled={loading}>{loading ? "Sorgulanıyor…" : "Karşılaştır"}</Button>
        <span className="pb-2 text-[11.5px] text-muted-foreground">
          {error ?? data?.notes?.[0] ?? "İki canlı API sorgulanır, birkaç saniye sürebilir."}
        </span>
      </Toolbar>

      {loading && !data && <Skeleton className="h-24 w-full rounded-xl" />}

      <StatGrid className="lg:grid-cols-4 xl:grid-cols-8">
        <StatCard label="AFAD kaydı" value={cat.AFAD ? fmtNum(cat.AFAD.count) : "—"} tone="warm" />
        <StatCard label="USGS kaydı" value={cat.USGS ? fmtNum(cat.USGS.count) : "—"} tone="cool" />
        <StatCard label="Eşleşen olay" value={cmp ? fmtNum(cmp.matched) : "—"} tone="success" />
        <StatCard label="Yalnız AFAD'da" value={cmp ? fmtNum(cmp.only_a) : "—"} tone="critical" />
        <StatCard label="Yalnız USGS'te" value={cmp ? fmtNum(cmp.only_b) : "—"} tone="critical" />
        <StatCard label="Medyan büyüklük farkı" value={st ? `${sign(st.dmag_median)}${st.dmag_median}` : "—"} />
        <StatCard label="Medyan episantr farkı" value={st ? `${st.dist_median} km` : "—"} />
        <StatCard label="En büyük episantr farkı" value={st ? `${st.dist_max} km` : "—"} />
      </StatGrid>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="glass-panel">
          <CardHeader className="pb-1"><CardTitle className="text-sm">Büyüklük Farkı Dağılımı (AFAD − USGS)</CardTitle></CardHeader>
          <CardContent className="h-[260px]">
            <Bar
              data={{ labels: binLabels,
                datasets: [{ label: "Olay", data: binLabels.map((l) => bins[l]),
                  backgroundColor: binLabels.map((l) => Math.abs(Number(l)) < 0.05 ? "rgba(132,204,22,0.6)" : "rgba(244,63,94,0.55)") }] }}
              options={{ ...baseChartOptions(), plugins: { ...baseChartOptions().plugins, legend: { display: false } } }} />
          </CardContent>
        </Card>

        <Card className="glass-panel">
          <CardHeader className="pb-1"><CardTitle className="text-sm">Episantr Farkı — Büyüklüğe Göre</CardTitle></CardHeader>
          <CardContent className="h-[260px]">
            <Scatter
              data={{ datasets: [{ label: "Eşleşen olaylar",
                data: pairs.map((p) => ({ x: Math.max(p.mag_a, p.mag_b), y: p.dist_km })),
                backgroundColor: "#38bdf8", pointRadius: 4 }] }}
              options={{
                ...baseChartOptions(),
                plugins: { ...baseChartOptions().plugins, legend: { display: false } },
                scales: {
                  x: { ...baseChartOptions().scales.x, title: { display: true, text: "Büyüklük", color: "#94a3b8" } },
                  y: { ...baseChartOptions().scales.y, title: { display: true, text: "Episantr farkı (km)", color: "#94a3b8" } },
                },
              }} />
          </CardContent>
        </Card>
      </div>

      <SectionTitle icon={Scale} title="Büyüklük Ölçeği Çiftleri" subtitle="Sistematik farklar" />
      <Card className="glass-panel">
        <CardContent className="pt-5">
          {cmp?.scale_pairs?.length ? (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>AFAD / USGS ölçeği</TableHead>
                    <TableHead className="text-center">Eşleşme</TableHead>
                    <TableHead className="text-center">Ortalama fark</TableHead>
                    <TableHead className="text-center">Medyan fark</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {cmp.scale_pairs.map((s) => (
                    <TableRow key={s.pair}>
                      <TableCell className="font-semibold">{s.pair}</TableCell>
                      <TableCell className="text-center tabular-nums">{s.n}</TableCell>
                      <TableCell className={`text-center font-bold tabular-nums ${Math.abs(s.dmag_mean) >= 0.2 ? "text-amber-400" : "text-muted-foreground"}`}>
                        {sign(s.dmag_mean)}{s.dmag_mean.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-center tabular-nums">{sign(s.dmag_median)}{s.dmag_median.toFixed(2)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <p className="mt-3 text-[11px] text-muted-foreground">
                Pozitif değer AFAD'ın daha büyük ölçtüğünü gösterir. Ölçekler farklı fiziksel
                büyüklükler ölçer; sistematik fark beklenen bir durumdur.
              </p>
            </>
          ) : <p className="text-[13px] text-muted-foreground">Ölçek kırılımı için yeterli eşleşme yok.</p>}
        </CardContent>
      </Card>

      <SectionTitle icon={GitCompareArrows} title="Eşleşen Olaylar" subtitle="En büyükten" />
      <Card className="glass-panel">
        <CardContent className="p-0">
          <ScrollArea className="h-[420px]">
            <Table>
              <TableHeader className="sticky top-0 bg-card/95 backdrop-blur">
                <TableRow>
                  <TableHead>Zaman (TSİ)</TableHead>
                  <TableHead className="text-center">AFAD</TableHead>
                  <TableHead className="text-center">USGS</TableHead>
                  <TableHead className="text-center">Fark</TableHead>
                  <TableHead className="text-center">Episantr</TableHead>
                  <TableHead className="text-center">Zaman farkı</TableHead>
                  <TableHead>Yer</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pairs.map((p, i) => (
                  <TableRow key={i} className={p.ambiguous ? "bg-amber-500/10" : ""}>
                    <TableCell className="whitespace-nowrap text-[12px]">{fmtTime(p.time_a)}</TableCell>
                    <TableCell className="text-center">
                      <b className="tabular-nums">M {p.mag_a.toFixed(1)}</b>
                      <span className="ml-1 text-[10.5px] text-muted-foreground">{p.magtype_a || "?"}</span>
                    </TableCell>
                    <TableCell className="text-center">
                      <b className="tabular-nums">M {p.mag_b.toFixed(1)}</b>
                      <span className="ml-1 text-[10.5px] text-muted-foreground">{p.magtype_b || "?"}</span>
                    </TableCell>
                    <TableCell className={`text-center font-bold tabular-nums ${Math.abs(p.dmag) >= 0.3 ? "text-amber-400" : "text-muted-foreground"}`}>
                      {sign(p.dmag)}{p.dmag.toFixed(1)}
                    </TableCell>
                    <TableCell className="text-center tabular-nums">{p.dist_km.toFixed(1)} km</TableCell>
                    <TableCell className="text-center tabular-nums">{p.dt_s.toFixed(0)} sn</TableCell>
                    <TableCell className="max-w-[220px] truncate text-[12px] text-muted-foreground">
                      {p.location_a}
                    </TableCell>
                  </TableRow>
                ))}
                {!pairs.length && (
                  <TableRow><TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                    Bu pencerede eşleşen olay bulunamadı.
                  </TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </ScrollArea>
        </CardContent>
      </Card>
      {cmp && cmp.ambiguous > 0 && (
        <p className="text-[11px] text-muted-foreground">
          <Badge variant="outline" className="mr-2 border-amber-500/40 text-amber-400">
            {cmp.ambiguous} belirsiz
          </Badge>
          Sarı satırlar, tolerans penceresinde birden fazla aday bulunduğu için eşleşmesi belirsiz olan olaylardır.
        </p>
      )}
    </div>
  )
}
