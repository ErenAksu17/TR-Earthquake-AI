import type { ChartData } from "chart.js"
import { useEffect, useState } from "react"
import { Bar, Scatter } from "react-chartjs-2"
import { CheckCircle2, Crosshair, Target, XCircle } from "lucide-react"
import { api, type ValidationAftershock, type ValidationIntensity } from "@/lib/api"
import { baseChartOptions, fmtNum } from "@/lib/seismic"
import { StatCard, StatGrid } from "@/components/StatCard"
import { InfoNote, CaveatList } from "@/components/InfoNote"
import { SectionTitle } from "@/components/SectionTitle"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Skeleton } from "@/components/ui/skeleton"

export function ValidationView() {
  const [intensity, setIntensity] = useState<ValidationIntensity | null>(null)
  const [aftershock, setAftershock] = useState<ValidationAftershock | null>(null)

  useEffect(() => {
    api.validationIntensity().then(setIntensity).catch(() => {})
    api.validationAftershock().then(setAftershock).catch(() => {})
  }, [])

  const o = intensity?.overall
  const sign = (x: number) => (x > 0 ? "+" : "")
  const bins = [...(intensity?.by_distance ?? []), ...(intensity?.by_magnitude ?? [])]

  return (
    <div className="flex flex-col gap-4">
      <InfoNote title="Bu araç kendi tahminlerini test ediyor">
        Bir modelin değeri, iddiasında değil gerçekle kıyaslandığında ne kadar tuttuğundadır.
        Burada iki bağımsız test var: şiddet modeli <b>USGS DYFI</b> gözlemlerine karşı,
        artçı şok tahmini ise <b>sözde-ileriye dönük N-testi</b> ile — model yalnızca ilk
        günlerin verisiyle kurulur, sonrası tahmin edilip gerçekleşenle kıyaslanır, geleceğe bakılmaz.
      </InfoNote>

      <SectionTitle icon={Crosshair} title="Şiddet Modeli" subtitle="Gözlenen vs tahmin edilen" />

      {!intensity && <Skeleton className="h-24 w-full rounded-xl" />}

      <StatGrid className="lg:grid-cols-5">
        <StatCard label="Gözlem" value={o ? fmtNum(o.observations) : "—"} tone="cool" />
        <StatCard label="Olay" value={o ? fmtNum(o.events) : "—"} tone="cool" />
        <StatCard label="Ortalama sapma" value={o ? `${sign(o.bias)}${o.bias.toFixed(2)} MMI` : "—"}
          tone={o && Math.abs(o.bias) < 0.15 ? "success" : "warm"} hint="0 = yansız" />
        <StatCard label="Ortalama mutlak hata" value={o ? `${o.mae.toFixed(2)} MMI` : "—"} tone="warm" />
        <StatCard label="±1 MMI içinde" value={o ? `%${(o.within_1_mmi * 100).toFixed(0)}` : "—"} tone="success" />
      </StatGrid>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="glass-panel">
          <CardHeader className="pb-1"><CardTitle className="text-sm">Gözlenen vs Tahmin Edilen Şiddet</CardTitle></CardHeader>
          <CardContent className="h-[300px]">
            {intensity && (
              <Scatter
                data={{
                  datasets: [
                    { label: "DYFI kutuları",
                      data: intensity.scatter.map((s) => ({ x: s.predicted, y: s.observed })),
                      backgroundColor: "rgba(56,189,248,0.45)", pointRadius: 2.5 },
                    { label: "birebir (mükemmel tahmin)",
                      data: [{ x: 2, y: 2 }, { x: 10, y: 10 }], type: "line" as const,
                      borderColor: "#f43f5e", borderDash: [6, 4], pointRadius: 0, borderWidth: 2 },
                  ],
                } as unknown as ChartData<"scatter">}
                options={{
                  ...baseChartOptions(),
                  scales: {
                    x: { ...baseChartOptions().scales.x, min: 2, max: 10,
                      title: { display: true, text: "Tahmin (MMI)", color: "#94a3b8" } },
                    y: { ...baseChartOptions().scales.y, min: 2, max: 10,
                      title: { display: true, text: "Gözlenen (MMI)", color: "#94a3b8" } },
                  },
                }} />
            )}
          </CardContent>
        </Card>

        <Card className="glass-panel">
          <CardHeader className="pb-1"><CardTitle className="text-sm">Sapma — Uzaklığa Göre</CardTitle></CardHeader>
          <CardContent className="h-[300px]">
            {intensity && (
              <Bar
                data={{
                  labels: intensity.by_distance.map((b) => `${b.range} km`),
                  datasets: [{ label: "Ortalama sapma (MMI)",
                    data: intensity.by_distance.map((b) => b.bias),
                    backgroundColor: intensity.by_distance.map((b) =>
                      b.bias > 0 ? "rgba(56,189,248,0.6)" : "rgba(244,63,94,0.6)") }],
                }}
                options={{ ...baseChartOptions(), plugins: { ...baseChartOptions().plugins, legend: { display: false } } }} />
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="glass-panel">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Sapmanın Dağılımı</CardTitle>
          <p className="text-[11px] text-muted-foreground">Pozitif = model az tahmin ediyor · negatif = fazla tahmin ediyor</p>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Grup</TableHead><TableHead>Aralık</TableHead>
                <TableHead className="text-center">Gözlem</TableHead>
                <TableHead className="text-center">Sapma</TableHead>
                <TableHead className="text-center">MAE</TableHead>
                <TableHead className="text-center">RMSE</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {bins.map((b, i) => (
                <TableRow key={i}>
                  <TableCell className="text-muted-foreground">{b.group}</TableCell>
                  <TableCell className="font-semibold">{b.range}</TableCell>
                  <TableCell className="text-center tabular-nums">{b.n}</TableCell>
                  <TableCell className={`text-center font-bold tabular-nums ${Math.abs(b.bias) >= 0.3 ? "text-amber-400" : "text-muted-foreground"}`}>
                    {sign(b.bias)}{b.bias.toFixed(2)}
                  </TableCell>
                  <TableCell className="text-center tabular-nums">{b.mae.toFixed(2)}</TableCell>
                  <TableCell className="text-center tabular-nums">{b.rmse.toFixed(2)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <SectionTitle icon={Target} title="Artçı Şok Tahmini" subtitle="Sözde-ileriye dönük CSEP N-testi" />

      <StatGrid className="lg:grid-cols-5">
        <StatCard label="Test edilen dizi"
          value={aftershock ? `${aftershock.tested} / ${aftershock.candidates}` : "—"} tone="cool" />
        <StatCard label="İki kat içinde"
          value={aftershock?.within_factor_2_rate != null
            ? `${aftershock.within_factor_2} (%${(aftershock.within_factor_2_rate * 100).toFixed(0)})` : "—"}
          tone="success" hint="operasyonel ölçüt" />
        <StatCard label="Gözlenen / beklenen"
          value={aftershock?.ratio_observed_expected != null ? aftershock.ratio_observed_expected.toFixed(2) : "—"}
          tone="warm" hint="1.00 = mükemmel" />
        <StatCard label="Medyan sapma"
          value={aftershock?.median_log10_ratio != null
            ? `${aftershock.median_log10_ratio > 0 ? "+" : ""}${aftershock.median_log10_ratio} log₁₀` : "—"}
          tone="warm" hint="0 = yansız" />
        <StatCard label="Poisson N-testi"
          value={aftershock?.tested ? `${aftershock.passed} (%${((aftershock.pass_rate ?? 0) * 100).toFixed(0)})` : "—"}
          hint="kümelenme yüzünden katı" />
      </StatGrid>

      <InfoNote title="Poisson N-testi neden düşük çıkıyor?" tone="warning">
        Katalog derinleştirildikten sonra beklenen artçı sayıları yüzlere çıktı; Poisson
        testinin kabul bandı <b>√N</b> ile daraldığı için toplam kalibrasyon iyi olsa bile
        tek tek diziler reddediliyor. Artçılar kümelenmiş olduğundan gerçek saçılım
        Poisson'dan geniştir. Bu yüzden yanına <b>"iki kat içinde"</b> oranı ve
        <b>medyan sapma</b> konuldu — operasyonel tahmin değerlendirmesinde kullanılan
        ölçütler bunlardır. Bu iki ölçüt modelin iyi kalibre olduğunu gösteriyor.
      </InfoNote>

      <Card className="glass-panel">
        <CardHeader className="pb-2"><CardTitle className="text-sm">Test Edilen Diziler</CardTitle></CardHeader>
        <CardContent className="p-0 pb-4">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-6">Ana şok</TableHead>
                <TableHead className="text-center">M</TableHead>
                <TableHead className="text-center">Mc</TableHead>
                <TableHead className="text-center">b</TableHead>
                <TableHead className="text-center">p</TableHead>
                <TableHead className="text-center">Beklenen</TableHead>
                <TableHead className="text-center">Gözlenen</TableHead>
                <TableHead className="text-center">Sonuç</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(aftershock?.sequences ?? []).map((s, i) => (
                <TableRow key={i}>
                  <TableCell className="pl-6">
                    <div className="font-medium">{s.time.slice(0, 10)}</div>
                    <div className="text-[11px] text-muted-foreground">{(s.location ?? "").slice(0, 28)}</div>
                  </TableCell>
                  <TableCell className="text-center font-bold tabular-nums">{s.magnitude.toFixed(1)}</TableCell>
                  <TableCell className="text-center tabular-nums">{s.mc.toFixed(1)}</TableCell>
                  <TableCell className="text-center tabular-nums">{s.b.toFixed(2)}</TableCell>
                  <TableCell className="text-center tabular-nums">{s.p.toFixed(2)}</TableCell>
                  <TableCell className="text-center tabular-nums">{s.expected.toFixed(1)}</TableCell>
                  <TableCell className="text-center font-bold tabular-nums">{s.observed}</TableCell>
                  <TableCell className="text-center">
                    {s.passed
                      ? <span className="inline-flex items-center gap-1 font-semibold text-emerald-400">
                          <CheckCircle2 className="size-3.5" /> geçti</span>
                      : <span className="inline-flex items-center gap-1 font-semibold text-rose-400">
                          <XCircle className="size-3.5" /> kaldı</span>}
                  </TableCell>
                </TableRow>
              ))}
              {!aftershock?.sequences?.length && (
                <TableRow><TableCell colSpan={8} className="py-8 text-center text-muted-foreground">
                  Yeterli veriye sahip dizi bulunamadı.
                </TableCell></TableRow>
              )}
            </TableBody>
          </Table>
          {aftershock && (
            <p className="px-6 pt-3 text-[11px] text-muted-foreground">
              {aftershock.skipped_insufficient_data} dizi, öğrenme penceresinde yeterli artçı
              içermediği için test edilemedi (katalog M≥4 eşiğinde). Hedef büyüklük her dizinin
              kendi tamlık eşiği (Mc) alınır.
            </p>
          )}
        </CardContent>
      </Card>

      <CaveatList items={intensity?.caveats ?? []} title="Doğrulamanın kendi sınırları" />
    </div>
  )
}
