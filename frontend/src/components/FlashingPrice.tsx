import { formatPrice } from "@/data/format";
import type { PriceUpdate } from "@/data/types";

const FLASH = { up: "flash-up", down: "flash-down", flat: "" };

/** Show a price; a new timestamp remounts the span, restarting the CSS flash. */
export function FlashingPrice({ update }: { update: PriceUpdate }) {
  return (
    <span key={update.timestamp} className={`rounded-sm px-1 ${FLASH[update.direction]}`}>
      {formatPrice(update.price)}
    </span>
  );
}
