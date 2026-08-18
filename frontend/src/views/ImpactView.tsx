import { useCallback, useEffect, useRef, useState } from "react"
import L from "leaflet"
import { Building2, Radio, Siren, Users } from "lucide-react"
import { api, type ImpactResponse, type Quake } from "@/lib/api"
import { fmtMillions, fmtNum, mmiColor } from "@/lib/seismic"
import { loadFaults, faultStyle, useLeafletMap } from "@/hooks/useLeafletMap"
import { StatCard, StatGrid } from "@/components/StatCard"
import { Toolbar, Field } from "@/components/Toolbar"
import { InfoNote, CaveatList } from "@/components/InfoNote"
import { SectionTitle } from "@/components/SectionTitle"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

export function ImpactView() {
  const [mag, setMag] = useState("7.5")
  const [lat, setLat] = useState("40.75")
  const [lon, setLon] = useState("29.90")
  const [depth, setDepth] = useState("10")
  const [mains, setMains] = useState<Quake[]>([])
  const [showShelters, setShowShelters] = useState(false)
  const [shelterNote, setShelterNote] = useState("")
  const [data, setData] = useState<ImpactResponse | null>(null)

  const { ref, map } = useLeafletMap([39.5, 33], 6)
  const layer = useRef<L.LayerGroup | null>(null)
  const shelters = useRef<L.GeoJSON | null>(null)

  useEffect(() => {
    api.mainshocks(6.5, 40).then((d) => setMains(d.mainshocks)).catch(() => {})
  }, [])

  useEffect(() => {
    if (!map.current) return
    let cancelled = false
    ;(async () => {
      const gj = await loadFaults()
      if (gj && !cancelled && map.current) {
        L.geoJSON(gj, { style: { ...faultStyle, opacity: 0.25 } }).addTo(map.current)
      }
    })()
    return () => { cancelled = true }
  }, [map])

  const run = useCallback(async () => {
    try {
      setData(await api.impact({ mag, lat, lon, depth }))
    } catch { setData(null) }
  }, [mag, lat, lon, depth])

  useEffect(() => { run() }, [run])

  // Harita çizimi
  useEffect(() => {
    if (!map.current || !data) return
    layer.current?.remove()
    const layers: L.Layer[] = []

    ;[...data.bands].reverse().forEach((b) => {
      if (!b.radius_km) return
      layers.push(
        L.circle([data.event.lat, data.event.lon], {
          radius: b.radius_km * 1000,
          color: b.color, weight: 1.5, fillColor: b.color, fillOpacity: 0.1,
          dashArray: b.beyond_model_range ? "6 6" : undefined,
        }).bindPopup(
          `<b>MMI ${b.roman}</b> — ${b.label}<br>~${b.radius_km.toFixed(0)} km` +
          `${b.beyond_model_range ? " (model sınırı)" : ""}<br>${b.settlements} yerleşim`
        )
      )
    })

    // Leaflet'in varsayılan ikonu bundler altında 404 verir; kendi işaretçimizi çiziyoruz
    layers.push(L.marker([data.event.lat, data.event.lon], {
      icon: L.divIcon({
        className: "",
        iconSize: [18, 18],
        iconAnchor: [9, 9],
        html: `<span style="display:block;width:18px;height:18px;border-radius:999px;
                 background:radial-gradient(circle,#fff 0%,#f43f5e 45%,transparent 70%);
                 border:2px solid #fff;box-shadow:0 0 12px 3px rgba(244,63,94,.85)"></span>`,
      }),
    }).bindPopup(
      `<b>M ${data.event.magnitude.toFixed(1)}</b><br>derinlik ${data.event.depth_km.toFixed(0)} km`))

    data.settlements.slice(0, 120).forEach((s) => {
      const c = mmiColor(s.mmi)
      layers.push(L.circleMarker([s.lat, s.lon], {
        radius: Math.max(3, Math.log10(Math.max(s.population, 10)) * 1.8),
        color: c, fillColor: c, fillOpacity: 0.85, weight: 0.6,
      }).bindPopup(
        `<b>${s.name}</b><br>MMI ${s.mmi.toFixed(1)} ± ${s.sigma.toFixed(2)} (${s.roman})<br>` +
        `${fmtNum(s.population)} kişi · ${s.distance_km} km`
      ))
    })

    layer.current = L.layerGroup(layers).addTo(map.current)
    const big = data.bands.find((b) => b.radius_km)
    if (big?.radius_km) {
      map.current.fitBounds(L.latLng(data.event.lat, data.event.lon).toBounds(big.radius_km * 2000))
    }
  }, [data, map])

  // Toplanma alanları
  useEffect(() => {
    if (!map.current) return
    if (!showShelters) {
      shelters.current?.remove()
      shelters.current = null
      setShelterNote("")
      return
    }
    if (!data) return
    let cancelled = false
    ;(async () => {
      const fc = await api.shelters({ lat: data.event.lat, lon: data.event.lon, radius_km: 120 })
        .catch(() => null)
      if (!fc || cancelled || !map.current) return
      shelters.current?.remove()
      shelters.current = L.geoJSON(fc, {
        pointToLayer: (f, latlng) => L.circleMarker(latlng, {
          radius: 4, color: "#34d399", fillColor: "#34d399", fillOpacity: 0.9, weight: 1,
        }).bindPopup(
          `<b>Toplanma alanı</b><br>${(f.properties as { name?: string })?.name || "(isimsiz)"}<br>` +
          `<small>OSM — liste eksiktir</small>`
        ),
      }).addTo(map.current)
      setShelterNote(fc.features.length
        ? `${fc.features.length} toplanma alanı (OSM, eksik veri)`
        : "Bu bölgede OSM'de kayıtlı toplanma alanı yok — resmî liste için AFAD.")
    })()
    return () => { cancelled = true }
  }, [showShelters, data, map])

  const pickEvent = (idx: string) => {
    const m = mains[Number(idx)]
    if (!m) return
    setMag(String(m.magnitude))
    setLat(m.latitude.toFixed(3))
    setLon(m.longitude.toFixed(3))
    setDepth(String(Math.max(1, Math.round(m.depth ?? 10))))
  }

  const strong = data?.bands.find((b) => b.mmi_min === 7.0)

  return (
    <div className="flex flex-col gap-4">
      <InfoNote title="Bir deprem nerede ne kadar hissedilir?">
        Sarsıntı şiddeti, <i>Allen, Wald &amp; Worden (2012)</i> makrosismik şiddet
        denklemiyle her il/ilçe merkezi için hesaplanır ve MMI derecesine çevrilir.
        Geçmiş bir depremi seçebilir veya kendi senaryonuzu kurabilirsiniz.
        <br /><br />
        <b>Bu bir hasar tahmini değildir.</b> Model nokta kaynak varsayar, zemin
        büyütmesini hesaba katmaz ve 300 km'ye kadar geçerlidir. Nüfus rakamları
        kaba mertebedir. Toplanma alanları OSM topluluk verisidir ve <b>eksiktir</b>.
      </InfoNote>

      <Toolbar>
        <Field label="Geçmiş deprem">
          <Select onValueChange={(v) => { const s = v == null ? "" : String(v); if (s) pickEvent(s) }}>
            <SelectTrigger className="w-[330px]">
              <SelectValue placeholder="— senaryo gir —">
                {(v: unknown) => {
                  const m = mains[Number(v)]
                  return m
                    ? `M ${m.magnitude.toFixed(1)} — ${(m.location ?? "?").slice(0, 26)}`
                    : "— senaryo gir —"
                }}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {mains.map((m, i) => (
                <SelectItem key={i} value={String(i)}>
                  M {m.magnitude.toFixed(1)} — {(m.location ?? "?").slice(0, 30)} ({m.eventDate.slice(0, 10)})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field label="Büyüklük">
          <Input type="number" step="0.1" value={mag} onChange={(e) => setMag(e.target.value)} className="w-[86px]" />
        </Field>
        <Field label="Enlem">
          <Input type="number" step="0.01" value={lat} onChange={(e) => setLat(e.target.value)} className="w-[104px]" />
        </Field>
        <Field label="Boylam">
          <Input type="number" step="0.01" value={lon} onChange={(e) => setLon(e.target.value)} className="w-[104px]" />
        </Field>
        <Field label="Derinlik (km)">
          <Input type="number" value={depth} onChange={(e) => setDepth(e.target.value)} className="w-[92px]" />
        </Field>
        <Button onClick={run}>Hesapla</Button>
        <label className="flex cursor-pointer items-center gap-2 pb-1.5 text-[13px]">
          <Checkbox checked={showShelters} onCheckedChange={(v) => setShowShelters(Boolean(v))} />
          Toplanma alanları
        </label>
        {shelterNote && <span className="pb-2 text-[11.5px] text-muted-foreground">{shelterNote}</span>}
      </Toolbar>

      <StatGrid>
        <StatCard label="En yüksek şiddet" value={data?.max_mmi ? `MMI ${data.max_mmi.toFixed(1)}` : "—"}
          icon={Siren} tone="critical" />
        <StatCard label="Etkilenen yerleşim" value={data ? fmtNum(data.total_settlements) : "—"}
          icon={Building2} tone="warm" />
        <StatCard label="Yaklaşık nüfus" value={data ? `~${fmtMillions(data.total_population)}` : "—"}
          icon={Users} tone="cool" hint="mertebe — ±%30" />
        <StatCard label="MMI VII+ nüfus" value={strong ? `~${fmtMillions(strong.population)}` : "yok"}
          icon={Radio} tone="success" />
      </StatGrid>

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <Card className="glass-panel overflow-hidden p-0">
          <div ref={ref} className="h-[480px] w-full" />
        </Card>

        <Card className="glass-panel">
          <CardHeader className="pb-2"><CardTitle className="text-sm">Şiddet Bantları</CardTitle></CardHeader>
          <CardContent className="px-4">
            <div className="flex flex-col">
              {data?.bands.length ? [...data.bands].reverse().map((b) => (
                <div key={b.roman} className="flex items-center gap-3 border-b border-border/60 py-2.5 last:border-0">
                  <span className="grid min-w-[46px] place-items-center rounded-md px-1.5 py-1 text-[12px] font-bold text-white"
                    style={{ background: b.color }}>{b.roman}</span>
                  <div className="min-w-0">
                    <div className="text-[13px] font-semibold">{b.label}</div>
                    <div className="text-[11px] text-muted-foreground">
                      {b.settlements} yerleşim · ~{(b.population / 1e6).toFixed(2)} milyon
                      {b.radius_km ? ` · ~${b.radius_km.toFixed(0)} km${b.beyond_model_range ? "+" : ""}` : ""}
                    </div>
                  </div>
                </div>
              )) : <p className="py-6 text-[13px] text-muted-foreground">Kayda değer şiddet beklenen yerleşim yok.</p>}
            </div>
          </CardContent>
        </Card>
      </div>

      <SectionTitle icon={Building2} title="En Çok Etkilenen Yerleşimler" subtitle="Şiddet sırasına göre" />
      <Card className="glass-panel">
        <CardContent className="p-0">
          <ScrollArea className="h-[400px]">
            <Table>
              <TableHeader className="sticky top-0 bg-card/95 backdrop-blur">
                <TableRow>
                  <TableHead>Yerleşim</TableHead>
                  <TableHead className="text-center">MMI</TableHead>
                  <TableHead className="text-center">Derece</TableHead>
                  <TableHead className="text-center">Uzaklık</TableHead>
                  <TableHead className="text-right">Yaklaşık nüfus</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(data?.settlements ?? []).slice(0, 100).map((s, i) => (
                  <TableRow key={i}>
                    <TableCell className="font-semibold">{s.name}</TableCell>
                    <TableCell className="text-center font-bold tabular-nums" style={{ color: mmiColor(s.mmi) }}>
                      {s.mmi.toFixed(1)}
                      <span className="ml-1 text-[10.5px] font-normal text-muted-foreground">±{s.sigma.toFixed(2)}</span>
                    </TableCell>
                    <TableCell className="text-center">{s.roman}</TableCell>
                    <TableCell className="text-center tabular-nums">{s.distance_km} km</TableCell>
                    <TableCell className="text-right tabular-nums">{fmtNum(s.population)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ScrollArea>
        </CardContent>
      </Card>

      <CaveatList items={data?.caveats ?? []} />
    </div>
  )
}
