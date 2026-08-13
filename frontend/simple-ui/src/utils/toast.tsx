/**
 * Centralized toast notifications — single API for all notification types.
 * Mount `GlobalToastRegistrar` once in `_app.tsx`.
 */
import { useEffect, useCallback, useRef } from "react";
import { useToast, type UseToastOptions } from "@chakra-ui/react";
import { formatInstitutionCopy } from "./institutionCopy";

export type ToastType = "success" | "error" | "warning" | "info";

export interface ShowToastOptions {
  type: ToastType;
  message: string;
  /** When true, only the message is shown (no type-based title). */
  messageOnly?: boolean;
  silent?: boolean;
}

const TOAST_PRESETS: Record<
  ToastType,
  Pick<UseToastOptions, "status" | "duration"> & { title: string }
> = {
  success: { status: "success", title: "Success", duration: 5000 },
  error: { status: "error", title: "Error", duration: 7000 },
  warning: { status: "warning", title: "Warning", duration: 5000 },
  info: { status: "info", title: "Info", duration: 4000 },
};

const DEFAULT_OPTIONS: Partial<UseToastOptions> = {
  position: "bottom",
  isClosable: true,
};

const DEDUPE_MS = 3000;
let lastDedupeKey = "";
let lastDedupeAt = 0;

type ToastFn = (options: UseToastOptions) => unknown;

let globalToast: ToastFn | null = null;
const pendingToasts: UseToastOptions[] = [];

function getToastDedupeKey(options: UseToastOptions): string {
  if (options.status === "error" && options.description) {
    return `error:${options.description}`;
  }
  return `${options.status ?? "info"}:${options.title ?? ""}:${options.description ?? ""}`;
}

function shouldSkipDuplicateToast(key: string): boolean {
  const now = Date.now();
  if (key === lastDedupeKey && now - lastDedupeAt < DEDUPE_MS) return true;
  lastDedupeKey = key;
  lastDedupeAt = now;
  return false;
}

function copyToastOptions(options: UseToastOptions): UseToastOptions {
  return {
    ...options,
    title:
      typeof options.title === "string"
        ? formatInstitutionCopy(options.title)
        : options.title,
    description:
      typeof options.description === "string"
        ? formatInstitutionCopy(options.description)
        : options.description,
  };
}

function showGlobalToast(options: UseToastOptions): void {
  if (typeof window === "undefined") return;
  const merged = copyToastOptions({ ...DEFAULT_OPTIONS, ...options });

  if (globalToast) {
    globalToast(merged);
    return;
  }
  pendingToasts.push(merged);
}

/**
 * Show a standardized toast. Type determines icon, color, title, duration, and position.
 */
export function showToast({
  type,
  message,
  messageOnly = false,
  silent = false,
}: ShowToastOptions): void {
  if (typeof window === "undefined" || silent || !message.trim()) return;

  const preset = TOAST_PRESETS[type];
  showGlobalToast({
    title: messageOnly ? undefined : preset.title,
    description: message,
    status: preset.status,
    duration: preset.duration,
  });
}

function registerGlobalToast(toast: ToastFn | null): void {
  globalToast = toast;
  if (!toast) return;
  pendingToasts.splice(0).forEach((options) => toast(options));
}

export function useToastWithDeduplication() {
  const toast = useToast();
  const activeKeysRef = useRef(new Set<string>());
  const timeoutRefsRef = useRef(
    new Map<string, ReturnType<typeof setTimeout>>(),
  );

  return useCallback(
    (options: UseToastOptions) => {
      const key = getToastDedupeKey(options);
      if (activeKeysRef.current.has(key) || shouldSkipDuplicateToast(key))
        return "";

      activeKeysRef.current.add(key);
      const originalOnCloseComplete = options.onCloseComplete;
      const cleanup = () => {
        activeKeysRef.current.delete(key);
        const timeoutId = timeoutRefsRef.current.get(key);
        if (timeoutId) {
          clearTimeout(timeoutId);
          timeoutRefsRef.current.delete(key);
        }
        originalOnCloseComplete?.();
      };

      const toastId = toast({
        ...DEFAULT_OPTIONS,
        ...copyToastOptions(options),
        onCloseComplete: cleanup,
      });
      const toastDuration =
        options.duration ?? DEFAULT_OPTIONS.duration ?? 5000;
      timeoutRefsRef.current.set(key, setTimeout(cleanup, toastDuration + 300));
      return toastId;
    },
    [toast],
  );
}

/** Wires Chakra toast into non-React code paths. Mount once in `_app.tsx`. */
export function GlobalToastRegistrar() {
  const toast = useToastWithDeduplication();

  useEffect(() => {
    registerGlobalToast(toast);
    return () => registerGlobalToast(null);
  }, [toast]);

  return null;
}
