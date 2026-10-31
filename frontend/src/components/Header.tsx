import { formatMoney, formatSignedMoney, gainClass } from "@/data/format";
import type { ConnectionStatus, Portfolio } from "@/data/types";

const STATUS = {
  connected: { label: "Live", dot: "bg-gain" },
  reconnecting: { label: "Reconnecting", dot: "bg-focus" },
  disconnected: { label: "Disconnected", dot: "bg-loss" },
};

function Figure({ label, value, tone = "" }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className={`text-lg leading-tight font-medium ${tone}`}>{value}</dd>
    </div>
  );
}

interface HeaderProps {
  portfolio: Portfolio | null;
  status: ConnectionStatus;
}

/** Show the live account totals and the price stream's connection state. */
export function Header({ portfolio, status }: HeaderProps) {
  const { label, dot } = STATUS[status];
  return (
    <header className="flex flex-wrap items-center gap-x-8 gap-y-1 bg-canvas px-3 py-1.5">
      <h1 className="text-2xl font-bold tracking-tight">FinAlly</h1>
      <dl className="flex items-center gap-8">
        <Figure label="Total value" value={portfolio ? formatMoney(portfolio.total_value) : "--"} />
        <Figure label="Cash" value={portfolio ? formatMoney(portfolio.cash_balance) : "--"} />
        <Figure
          label="Unrealized P&L"
          value={portfolio ? formatSignedMoney(portfolio.unrealized_pnl) : "--"}
          tone={gainClass(portfolio?.unrealized_pnl)}
        />
      </dl>
      <p role="status" className="ml-auto flex items-center gap-2 text-sm text-muted">
        <span aria-hidden className={`size-2 rounded-full ${dot}`} />
        {label}
      </p>
    </header>
  );
}
