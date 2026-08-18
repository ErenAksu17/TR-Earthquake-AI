import type { LucideIcon } from "lucide-react"
import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"

interface Props {
  label: string
  value: string | number
  hint?: string
  icon?: LucideIcon
  tone?: "default" | "critical" | "warm" | "cool" | "success"
  className?: string
}

const TONES: Record<string, string> = {
  default: "from-primary to-destructive",
  critical: "from-rose-500 to-red-700",
  warm: "from-amber-400 to-orange-600",
  cool: "from-sky-400 to-indigo-500",
  success: "from-emerald-400 to-teal-600",
}

export function StatCard({ label, value, hint, icon: Icon, tone = "default", className }: Props) {
  return (
    <Card className={cn(
      "hover-lift relative gap-0 overflow-hidden p-0 py-0 glass-panel",
      className
    )}>
      <div className={cn("absolute inset-y-0 left-0 w-1 bg-gradient-to-b", TONES[tone])} />
      <div className="flex items-start justify-between gap-3 py-3.5 pl-5 pr-4">
        <div className="min-w-0">
          <div className="truncate text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            {label}
          </div>
          <div className="mt-1 truncate text-[22px] font-bold leading-tight tabular-nums">
            {value}
          </div>
          {hint && <div className="mt-0.5 truncate text-[11px] text-muted-foreground">{hint}</div>}
        </div>
        {Icon && <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground/70" />}
      </div>
    </Card>
  )
}

export function StatGrid({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn(
      "grid gap-3 sm:grid-cols-2 lg:grid-cols-4",
      className
    )}>
      {children}
    </div>
  )
}
