"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { api, type OnboardingStatus } from "../lib/api";
import { Login, SignOutButton, useSession } from "./auth";
import { OnboardingWizard } from "./onboarding/wizard";
import { THEMES, useTheme, type Theme } from "./theme";
import { useWorkspace, WorkspaceProvider } from "./workspace";

const TABS = [
  { href: "/", label: "Home" },
  { href: "/plan", label: "Plan" },
  { href: "/shopping", label: "Shopping" },
  { href: "/pantry", label: "Pantry" },
] as const;

/** Top-level chrome for the signed-in app: brand, household switcher, settings,
 *  and the primary tab navigation. Gates on auth (shows Login when signed out). */
export function AppShell({ children }: { children: React.ReactNode }) {
  const session = useSession();
  if (session === undefined) return null; // loading
  if (session === null) return <Login />;
  return (
    <WorkspaceProvider>
      <ThemeSync />
      <OnboardingGate>
        <Chrome email={session.user.email}>{children}</Chrome>
      </OnboardingGate>
    </WorkspaceProvider>
  );
}

/** First-run gate: new users (no completed household) go through the onboarding
 *  wizard before reaching the app. Best-effort — any error falls through to the
 *  app rather than trapping the user. */
function OnboardingGate({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  useEffect(() => {
    api
      .onboardingStatus()
      .then(setStatus)
      .catch(() => setStatus({ needs_onboarding: false, household_id: null }));
  }, []);

  if (status === null) return null; // loading
  if (status.needs_onboarding) return <OnboardingWizard status={status} />;
  return <>{children}</>;
}

/** On sign-in, pull the user's saved theme from their profile and apply it, so the
 *  choice follows across devices. localStorage stays the instant pre-auth cache;
 *  this corrects it once we can read the profile. Pulls once per mount. */
function ThemeSync() {
  const { setTheme } = useTheme();
  const pulled = useRef(false);
  useEffect(() => {
    if (pulled.current) return;
    pulled.current = true;
    api
      .getMyTheme()
      .then(({ theme }) => {
        if (theme && (THEMES as readonly string[]).includes(theme)) {
          setTheme(theme as Theme);
        }
      })
      .catch(() => {}); // best-effort; localStorage value stands
  }, [setTheme]);
  return null;
}

function Chrome({
  email,
  children,
}: {
  email?: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const { households, householdId, setHouseholdId, error } = useWorkspace();

  return (
    <div className="min-h-screen bg-bg">
      <div className="mx-auto max-w-3xl px-5 pb-16 pt-7">
        {/* Header */}
        <header className="flex items-center justify-between gap-3">
          <Link href="/" className="font-display text-xl font-semibold tracking-tight">
            Mise<span className="text-accent">.</span>
          </Link>
          <div className="flex items-center gap-3">
            {households.length > 0 && (
              <select
                data-testid="household-select"
                value={householdId}
                onChange={(e) => setHouseholdId(e.target.value)}
                className="rounded-full border border-line bg-surface px-3 py-1.5 text-sm font-medium text-ink"
              >
                <option value="">— select —</option>
                {households.map((h) => (
                  <option key={h.id} value={h.id}>
                    {h.name}
                  </option>
                ))}
              </select>
            )}
            <Link
              href="/settings"
              aria-label="Settings"
              className={`text-sm font-medium ${
                pathname === "/settings" ? "text-accent-ink" : "text-muted hover:text-ink"
              }`}
            >
              Settings
            </Link>
            <SignOutButton email={email} />
          </div>
        </header>

        {/* Primary nav */}
        <nav className="mt-5 flex gap-1 border-b border-line">
          {TABS.map((t) => {
            const active = pathname === t.href;
            return (
              <Link
                key={t.href}
                href={t.href}
                data-testid={`nav-${t.label.toLowerCase()}`}
                className={`-mb-px border-b-2 px-3 py-2 text-sm font-semibold transition-colors ${
                  active
                    ? "border-accent text-ink"
                    : "border-transparent text-muted hover:text-ink"
                }`}
              >
                {t.label}
              </Link>
            );
          })}
        </nav>

        {error && (
          <div className="mt-4 whitespace-pre-wrap rounded border border-accent/30 bg-accent-soft px-3 py-2 text-sm text-accent-ink">
            {error}
          </div>
        )}

        <div className="mt-6">{children}</div>
      </div>
    </div>
  );
}

/** Shared section-label used across screens. */
export function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
      {children}
    </span>
  );
}
