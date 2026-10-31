import type { ReactNode } from "react";

interface PanelProps {
  title: string;
  aside?: ReactNode;
  className?: string;
  children: ReactNode;
}

/** A titled region of the terminal grid. */
export function Panel({ title, aside, className = "", children }: PanelProps) {
  return (
    <section aria-label={title} className={`flex min-h-0 min-w-0 flex-col bg-panel ${className}`}>
      <header className="flex h-8 shrink-0 items-center justify-between px-3">
        <h2 className="text-sm font-semibold text-muted">{title}</h2>
        {aside}
      </header>
      {children}
    </section>
  );
}
