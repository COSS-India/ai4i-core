import { useCallback, useEffect, useState } from "react";

export const SIDEBAR_COLLAPSED_WIDTH = "4.5rem";
export const SIDEBAR_EXPANDED_WIDTH = "16rem";
export const SIDEBAR_PIN_STORAGE_KEY = "ai4i.sidebarPinned";

function readPinned(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(SIDEBAR_PIN_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

/** Persist whether the nav stays expanded so labels remain visible. */
export function useSidebarPin() {
  const [pinned, setPinned] = useState(false);

  useEffect(() => {
    setPinned(readPinned());
  }, []);

  const togglePinned = useCallback(() => {
    setPinned((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(SIDEBAR_PIN_STORAGE_KEY, String(next));
      } catch {
        /* ignore quota / private mode */
      }
      return next;
    });
  }, []);

  return { pinned, togglePinned };
}
