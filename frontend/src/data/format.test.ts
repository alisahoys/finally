import { describe, expect, it } from "vitest";
import { formatMoney, formatPercent, formatPrice, formatSignedMoney, gainClass } from "./format";

describe("format", () => {
  it("formats money and prices", () => {
    expect(formatMoney(10012.4)).toBe("$10,012.40");
    expect(formatPrice(190.5)).toBe("190.50");
    expect(formatPrice(null)).toBe("--");
  });

  it("signs changes explicitly", () => {
    expect(formatSignedMoney(12.4)).toBe("+$12.40");
    expect(formatSignedMoney(-3.1)).toBe("-$3.10");
    expect(formatPercent(0.65)).toBe("+0.65%");
    expect(formatPercent(-1.2)).toBe("-1.20%");
    expect(formatPercent(null)).toBe("--");
  });

  it("picks a color for gains, losses and no change", () => {
    expect(gainClass(1)).toBe("text-gain");
    expect(gainClass(-1)).toBe("text-loss");
    expect(gainClass(0)).toBe("text-muted");
    expect(gainClass(null)).toBe("text-muted");
  });
});
