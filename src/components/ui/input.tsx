import * as React from "react"

import { cn } from "@/lib/utils"

/* M3 Filled Text Field: rounded-4 (rounded), filled container with surface-container-high background */
function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "file:text-foreground placeholder:text-on-surface-variant selection:bg-primary selection:text-primary-foreground",
        "flex h-12 w-full min-w-0 rounded px-3 pt-3 pb-1 text-base transition-[color,box-shadow] outline-none",
        "bg-surface-container-high border-0 border-b-2 border-outline focus:border-primary",
        "file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium",
        "disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
        "md:text-sm",
        className
      )}
      {...props}
    />
  )
}

export { Input }
