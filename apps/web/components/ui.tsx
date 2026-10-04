import type { ButtonHTMLAttributes, ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 ${className}`}>{children}</section>;
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "quiet" };

export function Button({ variant = "primary", className = "", ...props }: ButtonProps) {
  const styles = {
    primary: "bg-green-800 text-white hover:bg-green-900 disabled:bg-stone-300",
    secondary: "bg-white text-green-900 ring-2 ring-green-800 hover:bg-green-50 disabled:text-stone-400 disabled:ring-stone-300",
    quiet: "bg-transparent text-stone-700 underline hover:bg-stone-100",
  }[variant];
  return (
    <button
      {...props}
      className={`min-h-12 rounded-xl px-5 py-2 text-base font-semibold transition-colors disabled:cursor-not-allowed ${styles} ${className}`}
    />
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="rounded-xl bg-red-50 p-3 text-base text-red-900 ring-1 ring-red-200">
      {children}
    </p>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-base font-semibold text-stone-800">{label}</span>
      {children}
    </label>
  );
}

export const inputClass =
  "block min-h-12 w-full rounded-xl border border-stone-400 bg-white px-3 py-2 text-base text-stone-900 placeholder:text-stone-500";
