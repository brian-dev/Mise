"use client";

import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

// Core kit, built to the design tokens (theme-agnostic). Grows as we rebuild
// screens; this is the seed used by the new auth screen.

type Variant = "primary" | "secondary" | "ghost";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-white hover:bg-accent-ink",
  secondary: "bg-accent-soft text-accent-ink hover:brightness-95",
  ghost: "bg-transparent text-ink border border-line hover:bg-surface-2",
};

export function Button({
  variant = "primary",
  className = "",
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      className={`inline-flex items-center justify-center rounded font-semibold text-sm px-4 py-2.5 transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${VARIANTS[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

export function Card({
  className = "",
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={`bg-surface border border-line rounded-lg shadow-card ${className}`}>
      {children}
    </div>
  );
}

export function Input({ className = "", ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={`w-full rounded border border-line bg-surface px-3 py-2.5 text-ink placeholder:text-muted outline-none focus:border-accent ${className}`}
      {...props}
    />
  );
}

export function Label({ children }: { children: ReactNode }) {
  return (
    <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">{children}</span>
  );
}
