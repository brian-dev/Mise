"use client";

import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";

import { Button, Card, Input } from "../components/ui";
import { supabase } from "../lib/supabase";

/** Tracks the current Supabase session. `undefined` = still loading. */
export function useSession(): Session | null | undefined {
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);
  return session;
}

export function SignOutButton({ email }: { email?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-muted">
      <span data-testid="user-email">{email}</span>
      <button
        data-testid="sign-out"
        onClick={() => supabase.auth.signOut()}
        className="font-semibold text-accent-ink hover:underline"
      >
        Sign out
      </button>
    </span>
  );
}

/** Email/password sign-in + sign-up. Local stack auto-confirms, so sign-up
 *  returns a session immediately (no email step). */
export function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(mode: "in" | "up") {
    setBusy(true);
    setError(null);
    const fn =
      mode === "in"
        ? supabase.auth.signInWithPassword({ email, password })
        : supabase.auth.signUp({ email, password });
    const { error } = await fn;
    if (error) setError(error.message);
    setBusy(false);
  }

  return (
    <main className="min-h-screen grid place-items-center bg-bg px-4">
      <Card className="w-full max-w-sm p-7">
        <div className="font-display text-3xl font-semibold tracking-tight">
          Mise<span className="text-accent">.</span>
        </div>
        <p className="mt-1 text-muted">Plan. Shop. Cook. Repeat.</p>

        {error && (
          <div className="mt-4 rounded border border-accent/30 bg-accent-soft px-3 py-2 text-sm text-accent-ink">
            {error}
          </div>
        )}

        <div className="mt-5 space-y-3">
          <Input
            data-testid="login-email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <Input
            data-testid="login-password"
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        <div className="mt-5 flex gap-3">
          <Button data-testid="login-signin" onClick={() => run("in")} disabled={busy}>
            Sign in
          </Button>
          <Button
            data-testid="login-signup"
            variant="ghost"
            onClick={() => run("up")}
            disabled={busy}
          >
            Create account
          </Button>
        </div>
      </Card>
    </main>
  );
}
