import type { Config } from "tailwindcss";

// Colors/fonts/radius map to CSS variables defined per theme in app/globals.css,
// so switching the `data-theme` on <html> re-themes the whole app with no class
// changes. (Mobile will consume the same token values via NativeWind later.)
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        ink: "var(--ink)",
        muted: "var(--muted)",
        line: "var(--line)",
        accent: "var(--accent)",
        "accent-ink": "var(--accent-ink)",
        "accent-soft": "var(--accent-soft)",
        good: "var(--good)",
        warn: "var(--warn)",
      },
      fontFamily: {
        display: "var(--font-display)",
        sans: "var(--font-sans)",
      },
      borderRadius: {
        DEFAULT: "var(--radius)",
        lg: "var(--radius-lg)",
      },
      boxShadow: {
        card: "var(--shadow-card)",
      },
    },
  },
  plugins: [],
};

export default config;
