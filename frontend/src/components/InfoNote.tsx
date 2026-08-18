import { Info } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { cn } from "@/lib/utils"

interface Props {
  title: string
  children: React.ReactNode
  tone?: "info" | "warning"
  className?: string
}

export function InfoNote({ title, children, tone = "info", className }: Props) {
  return (
    <Alert className={cn(
      "glass-panel border-l-4",
      tone === "warning" ? "border-l-amber-500" : "border-l-sky-500",
      className
    )}>
      <Info className={cn("size-4", tone === "warning" ? "text-amber-500" : "text-sky-400")} />
      <AlertTitle className="font-semibold">{title}</AlertTitle>
      <AlertDescription className="text-[13px] leading-relaxed text-muted-foreground">
        {children}
      </AlertDescription>
    </Alert>
  )
}

export function CaveatList({ items, title = "Sınırlar" }: { items: string[]; title?: string }) {
  if (!items?.length) return null
  return (
    <InfoNote title={title} tone="warning">
      <ul className="ml-4 list-disc space-y-1">
        {items.map((c, i) => <li key={i}>{c}</li>)}
      </ul>
    </InfoNote>
  )
}
