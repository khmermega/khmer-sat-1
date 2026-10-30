import type { ReactNode } from "react";

interface PanelProps {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
  testId?: string;
}

export function Panel({ title, subtitle, actions, className = "", bodyClassName = "", children, testId }: PanelProps) {
  return (
    <section
      data-testid={testId}
      className={`flex min-w-0 flex-col rounded-xl border border-line bg-panel/90 shadow-[0_0_0_1px_rgba(255,255,255,0.02),0_20px_40px_-20px_rgba(0,0,0,0.6)] backdrop-blur ${className}`}
    >
      <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
        <div className="min-w-0">
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-ink-2">{title}</h2>
          {subtitle && <div className="mt-0.5 truncate text-[11px] text-ink-3">{subtitle}</div>}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </header>
      <div className={`min-h-0 flex-1 p-4 ${bodyClassName}`}>{children}</div>
    </section>
  );
}

export function Chip({ className = "", children }: { className?: string; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ring-1 ring-inset ${className}`}>
      {children}
    </span>
  );
}

export function Button({
  children,
  onClick,
  variant = "default",
  disabled,
  type = "button",
  className = "",
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "default" | "primary" | "danger" | "ghost";
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
  title?: string;
}) {
  const styles = {
    default: "bg-panel-2 text-ink ring-line-2 hover:bg-line hover:ring-ink-3",
    primary: "bg-gold/90 text-void ring-gold hover:bg-gold font-semibold",
    danger: "bg-crit/15 text-crit ring-crit/50 hover:bg-crit/25",
    ghost: "bg-transparent text-ink-2 ring-transparent hover:bg-panel-2 hover:text-ink",
  }[variant];
  return (
    <button
      type={type}
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-xs ring-1 ring-inset transition disabled:cursor-not-allowed disabled:opacity-40 ${styles} ${className}`}
    >
      {children}
    </button>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-[11px] text-ink-3">
      <span className="uppercase tracking-wider">{label}</span>
      {children}
    </label>
  );
}

export const inputCls =
  "w-full rounded-lg border border-line-2 bg-deck px-2.5 py-1.5 text-xs text-ink outline-none placeholder:text-ink-3 focus:border-sky/60 focus:ring-2 focus:ring-sky/20";
