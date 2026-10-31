const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const price = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const shares = new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 });

export const formatMoney = (value: number) => money.format(value);

export const formatPrice = (value: number | null | undefined) =>
  value == null ? "--" : price.format(value);

export const formatShares = (value: number) => shares.format(value);

/** Format a dollar change with an explicit sign, such as +$12.40 or -$3.10. */
export function formatSignedMoney(value: number) {
  return `${value < 0 ? "-" : "+"}${money.format(Math.abs(value))}`;
}

/** Format a value in percent units, so 0.65 becomes +0.65%. */
export function formatPercent(value: number | null | undefined) {
  if (value == null) return "--";
  return `${value < 0 ? "" : "+"}${value.toFixed(2)}%`;
}

/** Return the text color class for a gain, a loss or no change. */
export function gainClass(value: number | null | undefined) {
  if (!value) return "text-muted";
  return value > 0 ? "text-gain" : "text-loss";
}
