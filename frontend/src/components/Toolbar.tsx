import { cn } from "@/lib/utils"

export function Toolbar({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn(
      "glass-panel flex flex-wrap items-end gap-3 rounded-xl px-4 py-3",
      className
    )}>
      {children}
    </div>
  )
}

export function Field({ label, children, className }: {
  label: string; children: React.ReactNode; className?: string
}) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <span className="text-[10.5px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      {children}
    </div>
  )
}
