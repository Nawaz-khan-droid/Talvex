import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  /* M3: Filled button base = rounded-full, Outlined = rounded-2xl */
  "inline-flex items-center justify-center gap-2 whitespace-nowrap text-sm font-medium transition-all disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive",
  {
    variants: {
      variant: {
        /* M3 Filled Button: rounded-full, no border */
        default:
          "bg-primary text-primary-foreground shadow-xs hover:bg-primary/90 rounded-full",
        /* M3 Filled Tonal Button */
        secondary:
          "bg-secondary-container text-on-secondary-container shadow-xs hover:bg-secondary-container/80 rounded-full",
        /* M3 Outlined Button: rounded-2xl, border */
        outline:
          "border border-outline bg-transparent hover:bg-primary/8 hover:text-on-surface rounded-2xl",
        /* M3 Filled Button (destructive): rounded-full */
        destructive:
          "bg-destructive text-destructive-foreground shadow-xs hover:bg-destructive/90 focus-visible:ring-destructive/20 dark:focus-visible:ring-destructive/40 rounded-full",
        /* M3 Text Button: no border, no fill */
        ghost:
          "hover:bg-primary/8 hover:text-on-surface",
        /* M3 Text Button (link) */
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-6 py-2 has-[>svg]:px-4",
        sm: "h-8 rounded-full gap-1.5 px-4 has-[>svg]:px-3 text-xs",
        lg: "h-12 rounded-full px-8 has-[>svg]:px-5 text-base",
        /* M3 Icon Button: rounded-full */
        icon: "size-10 rounded-full",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot : "button"

  return (
    <Comp
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
