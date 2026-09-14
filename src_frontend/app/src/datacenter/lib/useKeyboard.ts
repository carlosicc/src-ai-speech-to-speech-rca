import { useEffect, useRef, type MutableRefObject } from "react";

const TRACKED = new Set([
  "arrowup", "arrowdown", "arrowleft", "arrowright",
  "w", "a", "s", "d", "shift",
]);

export function isTypingInField(): boolean {
  const el = document.activeElement;
  return el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement;
}

/** Set of currently held keys (lower-cased `KeyboardEvent.key`). Clears on window blur. */
export function useKeyboard(): MutableRefObject<Set<string>> {
  const keys = useRef(new Set<string>());

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (isTypingInField()) return;
      if (e.metaKey || e.ctrlKey) return;
      const k = e.key.toLowerCase();
      if (!TRACKED.has(k)) return;
      keys.current.add(k);
      if (k.startsWith("arrow")) e.preventDefault(); // stop page scroll
    };
    const up = (e: KeyboardEvent) => {
      keys.current.delete(e.key.toLowerCase());
    };
    const clear = () => keys.current.clear();

    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    window.addEventListener("blur", clear);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      window.removeEventListener("blur", clear);
    };
  }, []);

  return keys;
}
