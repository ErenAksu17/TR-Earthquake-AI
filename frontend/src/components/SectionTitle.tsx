import type { LucideIcon } from "lucide-react"

export function SectionTitle({ icon: Icon, title, subtitle }: {
  icon?: LucideIcon; title: string; subtitle?: string
}) {
  return (
    <div className="flex items-center gap-2.5 pt-1">
      {Icon && (
        <span className="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-primary/25 to-destructive/25 text-primary">
          <Icon className="size-4" />
        </span>
      )}
      <div>
        <h2 className="text-[15px] font-bold leading-tight">{title}</h2>
        {subtitle && <p className="text-[11.5px] text-muted-foreground">{subtitle}</p>}
      </div>
    </div>
  )
}
