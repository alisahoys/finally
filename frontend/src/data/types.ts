export type Direction = "up" | "down" | "flat";

export interface PriceUpdate {
  ticker: string;
  price: number;
  previous_price: number;
  open_price: number;
  timestamp: number;
  change: number;
  change_percent: number;
  session_change_percent: number;
  direction: Direction;
}

export type PriceMap = Record<string, PriceUpdate>;

export type ConnectionStatus = "connected" | "reconnecting" | "disconnected";

export interface Position {
  ticker: string;
  quantity: number;
  avg_cost: number;
  current_price: number | null;
  market_value: number;
  unrealized_pnl: number;
  pnl_percent: number;
}

export interface Portfolio {
  cash_balance: number;
  total_value: number;
  unrealized_pnl: number;
  positions: Position[];
}

export type Side = "buy" | "sell";

export interface Trade {
  id: string;
  ticker: string;
  side: Side;
  quantity: number;
  price: number;
  executed_at: string;
}

export interface TradeResult {
  trade: Trade;
  portfolio: Portfolio;
}

export interface Snapshot {
  total_value: number;
  recorded_at: string;
}

export interface WatchlistEntry {
  ticker: string;
  price: number | null;
  open_price: number | null;
  session_change_percent: number | null;
  added_at: string;
}

interface ActionOutcome {
  status: "ok" | "error";
  error?: string;
}

export interface TradeAction extends ActionOutcome {
  type: "trade";
  ticker: string;
  side: Side;
  quantity: number;
  price?: number;
}

export interface WatchlistAction extends ActionOutcome {
  type: "watchlist";
  ticker: string;
  action: "add" | "remove";
}

export type ChatAction = TradeAction | WatchlistAction;

export interface ChatReply {
  message: string;
  actions: ChatAction[];
}
