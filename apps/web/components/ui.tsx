"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type {
  ButtonHTMLAttributes,
  HTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
} from "react";

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
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`bg-surface border border-line rounded-lg shadow-card ${className}`}
      {...props}
    >
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

/** Small "i" affordance that reveals a short explanation on click. Closes on
 *  outside click or Escape. Use beside a form-field label. */
export function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <span ref={ref} className="relative inline-flex">
      <button
        type="button"
        aria-label={`About ${label}`}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="grid h-4 w-4 place-items-center rounded-full border border-line text-[10px] font-semibold leading-none text-muted hover:border-accent hover:text-accent-ink"
      >
        i
      </button>
      {open && (
        <span
          role="tooltip"
          className="absolute left-0 top-6 z-10 w-60 rounded-md border border-line bg-surface p-3 text-xs font-normal leading-relaxed text-ink shadow-card"
        >
          {children}
        </span>
      )}
    </span>
  );
}

/** Square recipe thumbnail with a graceful fallback when there's no image yet
 *  (representative stock photos, not exact-dish renders — UX_DESIGN.md §8). */
export function Thumb({
  src,
  alt,
  size = 44,
  className = "",
}: {
  src: string | null;
  alt: string;
  size?: number;
  className?: string;
}) {
  const style = { width: size, height: size };
  if (src) {
    // eslint-disable-next-line @next/next/no-img-element
    return (
      <img
        src={src}
        alt={alt}
        style={style}
        className={`shrink-0 rounded-md border border-line object-cover ${className}`}
      />
    );
  }
  return (
    <div
      style={style}
      aria-hidden
      className={`grid shrink-0 place-items-center rounded-md border border-line bg-surface-2 text-muted ${className}`}
    >
      <svg width={size * 0.5} height={size * 0.5} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 2v7a3 3 0 0 0 3 3v10M6 2v6M9 2v6M9 2v7a3 3 0 0 1-3 3" />
        <path d="M18 2c-1.5 0-3 1.8-3 5s1.5 4 3 4v9" />
      </svg>
    </div>
  );
}

/** Modal dialog: dimmed backdrop, focus moves into the panel, Escape or a
 *  backdrop click cancels. Keep content short — this is for quick confirms. */
export function Dialog({
  title,
  onClose,
  children,
  ...props
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
} & HTMLAttributes<HTMLDivElement>) {
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    panel.current?.querySelector<HTMLElement>("input, button")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      prev?.focus();
    };
  }, [onClose]);

  // Portal to <body> so no transformed/animated ancestor can clip the scrim.
  return createPortal(
    <div
      className="fixed inset-0 z-50 grid place-items-center px-4"
      // Theme colors are CSS vars (no alpha channel), so the scrim is a plain rgba.
      style={{ background: "rgba(20, 16, 12, 0.35)" }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-lg border border-line bg-surface p-5 shadow-card"
        {...props}
      >
        <h2 className="font-display text-lg font-semibold">{title}</h2>
        <div className="mt-3">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
