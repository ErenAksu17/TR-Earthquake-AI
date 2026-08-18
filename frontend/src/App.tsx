import { useState } from "react"
import {
  Activity, BarChart3, CheckCircle2, Globe2, Microscope, Radio, Scale,
} from "lucide-react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { LiveView } from "@/views/LiveView"
import { ArchiveView } from "@/views/ArchiveView"
import { SeismologyView } from "@/views/SeismologyView"
import { CompareView } from "@/views/CompareView"
import { ImpactView } from "@/views/ImpactView"
import { ValidationView } from "@/views/ValidationView"
import { cn } from "@/lib/utils"

const TABS = [
  { id: "live", label: "Canlı", icon: Radio },
  { id: "archive", label: "Arşiv & Analiz", icon: BarChart3 },
  { id: "seismo", label: "Sismoloji", icon: Microscope },
  { id: "compare", label: "Kaynak Karşılaştırma", icon: Scale },
  { id: "impact", label: "Etki Analizi", icon: Activity },
  { id: "validation", label: "Doğrulama", icon: CheckCircle2 },
]

export default function App() {
  const [online, setOnline] = useState<boolean | null>(null)
  const [tab, setTab] = useState("live")

  return (
    <div className="app-shell min-h-screen">
      <Tabs value={tab} onValueChange={setTab} className="gap-0">
        <header className="sticky top-0 z-[500] border-b border-border/70 bg-background/80 backdrop-blur-xl">
          <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-6 gap-y-3 px-5 py-3">
            <div className="flex items-center gap-3">
              <span className="grid size-10 place-items-center rounded-xl bg-gradient-to-br from-amber-400 via-orange-500 to-rose-600 shadow-lg shadow-orange-500/25">
                <Globe2 className="size-5 text-white" />
              </span>
              <div>
                <h1 className="text-[17px] font-extrabold leading-tight tracking-tight">
                  TR <span className="text-seismic-gradient">Earthquake AI</span>
                </h1>
                <p className="text-[10.5px] text-muted-foreground">
                  Türkiye Deprem Analiz Platformu
                </p>
              </div>
            </div>

            <TabsList className="h-auto flex-wrap gap-1 bg-secondary/45 p-1">
              {TABS.map(({ id, label, icon: Icon }) => (
                <TabsTrigger key={id} value={id}
                  className="gap-1.5 px-3 py-1.5 text-[12.5px] data-[state=active]:bg-gradient-to-br data-[state=active]:from-orange-500 data-[state=active]:to-rose-600 data-[state=active]:text-white data-[state=active]:shadow-md">
                  <Icon className="size-3.5" /> {label}
                </TabsTrigger>
              ))}
            </TabsList>

            <div className="ml-auto flex items-center gap-2 text-[11.5px] text-muted-foreground">
              <span className={cn("size-2 rounded-full",
                online === null ? "bg-muted-foreground/50"
                  : online ? "bg-emerald-400 pulse-dot" : "bg-rose-500")} />
              {online === null ? "bağlanıyor…" : online ? "canlı veri aktif" : "kaynaklara erişilemiyor"}
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1600px] px-5 py-5">
          <TabsContent value="live" className="mt-0"><LiveView onStatus={setOnline} /></TabsContent>
          <TabsContent value="archive" className="mt-0">{tab === "archive" && <ArchiveView />}</TabsContent>
          <TabsContent value="seismo" className="mt-0">{tab === "seismo" && <SeismologyView />}</TabsContent>
          <TabsContent value="compare" className="mt-0">{tab === "compare" && <CompareView />}</TabsContent>
          <TabsContent value="impact" className="mt-0">{tab === "impact" && <ImpactView />}</TabsContent>
          <TabsContent value="validation" className="mt-0">{tab === "validation" && <ValidationView />}</TabsContent>
        </main>
      </Tabs>

      <footer className="border-t border-border/70 px-5 py-4 text-center text-[11px] text-muted-foreground">
        Veriler: Kandilli Rasathanesi · AFAD · USGS · GeoNames · OpenStreetMap
        &nbsp;|&nbsp; Zamanlar Türkiye saatine (UTC+3) çevrilir
        &nbsp;|&nbsp; Bu araç resmî deprem tahmini yapmaz.
      </footer>
    </div>
  )
}
