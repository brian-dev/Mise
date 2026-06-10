"use client";

import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";

import { supabase } from "../lib/supabase";

const card: React.CSSProperties = {
  border: "1px solid #e2ddd2",
  borderRadius: 10,
  padding: "1.25rem",
  maxWidth: 360,
  margin: "4rem auto",
  background: "#fff",
};

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
    <span style={{ float: "right", fontSize: 14, color: "#6b6256" }}>
      <span data-testid="user-email">{email}</span>{" "}
      <button
        data-testid="sign-out"
        onClick={() => supabase.auth.signOut()}
        style={{ marginLeft: 8 }}
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
    <main style={{ fontFamily: "system-ui" }}>
      <div style={card}>
        <h1 style={{ marginTop: 0 }}>Mise</h1>
        <p style={{ color: "#6b6256" }}>Sign in to plan your meals.</p>
        {error && <div style={{ color: "#c0392b", marginBottom: 8 }}>{error}</div>}
        <input
          data-testid="login-email"
          placeholder="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          style={{ display: "block", width: "100%", padding: 8, marginBottom: 8 }}
        />
        <input
          data-testid="login-password"
          type="password"
          placeholder="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          style={{ display: "block", width: "100%", padding: 8, marginBottom: 12 }}
        />
        <button
          data-testid="login-signin"
          onClick={() => run("in")}
          disabled={busy}
          style={{ marginRight: 8 }}
        >
          Sign in
        </button>
        <button data-testid="login-signup" onClick={() => run("up")} disabled={busy}>
          Sign up
        </button>
      </div>
    </main>
  );
}
