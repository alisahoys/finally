import { useEffect, useRef, useState } from "react";
import { appendPrices, type PriceHistory } from "@/data/history";
import type { ConnectionStatus, PriceMap } from "@/data/types";

const REOPEN_DELAY_MS = 2000;

/** Subscribe to live prices, accumulating per-ticker history since page load. */
export function usePriceStream() {
  const [prices, setPrices] = useState<PriceMap>({});
  const [status, setStatus] = useState<ConnectionStatus>("reconnecting");
  const history = useRef<PriceHistory>({});

  useEffect(() => {
    let source: EventSource;
    let reopen: ReturnType<typeof setTimeout>;

    function open() {
      source = new EventSource("/api/stream/prices");
      source.onopen = () => setStatus("connected");
      source.onmessage = (event) => {
        const update: PriceMap = JSON.parse(event.data);
        appendPrices(history.current, update);
        setPrices(update);
      };
      source.onerror = () => {
        // The browser retries dropped connections itself but gives up on HTTP errors.
        if (source.readyState === EventSource.CONNECTING) return setStatus("reconnecting");
        setStatus("disconnected");
        reopen = setTimeout(open, REOPEN_DELAY_MS);
      };
    }

    open();
    return () => {
      clearTimeout(reopen);
      source.close();
    };
  }, []);

  return { prices, status, history: history.current };
}
