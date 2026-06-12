"use client";

import { Card } from "../../components/ui";
import { SectionLabel } from "../shell";
import { THEME_LABELS, THEMES, useTheme, type Theme } from "../theme";

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();

  return (
    <Card className="p-5">
      <SectionLabel>Appearance</SectionLabel>
      <h3 className="mt-2 font-display text-lg font-semibold">Theme</h3>
      <p className="mt-1 text-sm text-muted">Pick the look that suits you. Saved on this device.</p>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3" data-testid="theme-picker">
        {THEMES.map((t) => (
          <ThemeOption
            key={t}
            theme={t}
            active={t === theme}
            onSelect={() => setTheme(t)}
          />
        ))}
      </div>
    </Card>
  );
}

const SWATCHES: Record<Theme, { bg: string; surface: string; accent: string }> = {
  warm: { bg: "#f6f1e7", surface: "#fffdf8", accent: "#c0532f" },
  fresh: { bg: "#f4f6f4", surface: "#ffffff", accent: "#1f9d6b" },
  dark: { bg: "#16140f", surface: "#211e18", accent: "#d2a24c" },
};

function ThemeOption({
  theme,
  active,
  onSelect,
}: {
  theme: Theme;
  active: boolean;
  onSelect: () => void;
}) {
  const s = SWATCHES[theme];
  return (
    <button
      data-testid={`theme-${theme}`}
      onClick={onSelect}
      className={`rounded-lg border p-3 text-left transition-colors ${
        active ? "border-accent ring-1 ring-accent" : "border-line hover:bg-surface-2"
      }`}
    >
      <div
        className="flex h-12 items-center gap-1.5 rounded-md px-2"
        style={{ background: s.bg }}
      >
        <span
          className="h-6 w-6 rounded-full border"
          style={{ background: s.surface, borderColor: "rgba(0,0,0,0.08)" }}
        />
        <span className="h-6 w-6 rounded-full" style={{ background: s.accent }} />
      </div>
      <div className="mt-2 flex items-center justify-between">
        <span className="text-sm font-semibold">{THEME_LABELS[theme]}</span>
        {active && <span className="text-xs font-medium text-accent-ink">Active</span>}
      </div>
    </button>
  );
}
