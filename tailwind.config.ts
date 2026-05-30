import type { Config } from "tailwindcss";
import tailwindcssAnimate from "tailwindcss-animate";

const config: Config = {
    darkMode: "class",
    content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
        extend: {
                colors: {
                        background: 'var(--background)',
                        foreground: 'var(--foreground)',
                        card: {
                                DEFAULT: 'var(--card)',
                                foreground: 'var(--card-foreground)'
                        },
                        popover: {
                                DEFAULT: 'var(--popover)',
                                foreground: 'var(--popover-foreground)'
                        },
                        primary: {
                                DEFAULT: 'var(--primary)',
                                foreground: 'var(--primary-foreground)',
                                container: 'var(--primary-container)',
                                "on-container": 'var(--on-primary-container)',
                        },
                        secondary: {
                                DEFAULT: 'var(--secondary)',
                                foreground: 'var(--secondary-foreground)',
                                container: 'var(--secondary-container)',
                                "on-container": 'var(--on-secondary-container)',
                        },
                        tertiary: {
                                DEFAULT: 'var(--tertiary)',
                                container: 'var(--tertiary-container)',
                        },
                        muted: {
                                DEFAULT: 'var(--muted)',
                                foreground: 'var(--muted-foreground)'
                        },
                        accent: {
                                DEFAULT: 'var(--accent)',
                                foreground: 'var(--accent-foreground)'
                        },
                        destructive: {
                                DEFAULT: 'var(--destructive)',
                                foreground: 'var(--destructive-foreground)',
                                container: 'var(--error-container)',
                        },
                        border: 'var(--border)',
                        input: 'var(--input)',
                        ring: 'var(--ring)',
                        outline: 'var(--outline)',
                        "surface-container": 'var(--surface-container)',
                        "surface-container-high": 'var(--surface-container-high)',
                        "surface-container-highest": 'var(--surface-container-highest)',
                        chart: {
                                '1': 'var(--chart-1)',
                                '2': 'var(--chart-2)',
                                '3': 'var(--chart-3)',
                                '4': 'var(--chart-4)',
                                '5': 'var(--chart-5)'
                        },
                        sidebar: {
                                DEFAULT: 'var(--sidebar)',
                                foreground: 'var(--sidebar-foreground)',
                                primary: 'var(--sidebar-primary)',
                                "primary-foreground": 'var(--sidebar-primary-foreground)',
                                accent: 'var(--sidebar-accent)',
                                "accent-foreground": 'var(--sidebar-accent-foreground)',
                                border: 'var(--sidebar-border)',
                                ring: 'var(--sidebar-ring)',
                        },
                },
                borderRadius: {
                        sm: 'var(--radius-sm)',
                        md: 'var(--radius-md)',
                        lg: 'var(--radius-lg)',
                        xl: 'var(--radius-xl)',
                        '2xl': 'var(--radius-2xl)',
                        '3xl': 'var(--radius-3xl)',
                },
                /* M3 Motion — easing curves from the Material Design spec */
                transitionTimingFunction: {
                        'm3-standard': 'cubic-bezier(0.2, 0, 0, 1)',
                        'm3-standard-decelerate': 'cubic-bezier(0, 0, 0, 1)',
                        'm3-standard-accelerate': 'cubic-bezier(0.3, 0, 0.8, 0.15)',
                        'm3-emphasized': 'cubic-bezier(0.2, 0, 0, 1)',
                        'm3-emphasized-decelerate': 'cubic-bezier(0.05, 0.7, 0.1, 1)',
                        'm3-emphasized-accelerate': 'cubic-bezier(0.3, 0, 0.8, 0.15)',
                },
                /* M3 Motion — durations from the Material Design spec */
                transitionDuration: {
                        'm3-short1': '50ms',
                        'm3-short2': '100ms',
                        'm3-short3': '150ms',
                        'm3-short4': '200ms',
                        'm3-medium1': '250ms',
                        'm3-medium2': '300ms',
                        'm3-medium3': '350ms',
                        'm3-medium4': '400ms',
                        'm3-long1': '450ms',
                        'm3-long2': '500ms',
                },
                /* M3 Elevation — tonal surface levels (replaces drop shadows) */
                boxShadow: {
                        'm3-0': 'none',
                        'm3-1': '0 1px 3px 1px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06)',
                        'm3-2': '0 2px 6px 4px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04)',
                        'm3-3': '0 4px 8px 3px rgba(0,0,0,0.08), 0 1px 3px rgba(0,0,0,0.04)',
                        'm3-4': '0 6px 10px 4px rgba(0,0,0,0.08), 0 2px 4px rgba(0,0,0,0.04)',
                        'm3-5': '0 8px 12px 6px rgba(0,0,0,0.08), 0 2px 4px rgba(0,0,0,0.04)',
                },
                fontFamily: {
                        sans: ['var(--font-roboto)', 'Roboto', 'Google Sans', 'system-ui', '-apple-system', 'sans-serif'],
                },
        }
  },
  plugins: [tailwindcssAnimate],
};
export default config;
