/**
 * Centralized toast notifications — Chakra UI under the hood.
 * Use `useToastWithDeduplication()` in components, `showGlobalToast()` elsewhere.
 */
import { useEffect, useCallback, useRef } from 'react';
import { useToast, type UseToastOptions } from '@chakra-ui/react';

const DEFAULT_OPTIONS: Partial<UseToastOptions> = {
  position: 'bottom',
  duration: 5000,
  isClosable: true,
};

type ToastFn = (options: UseToastOptions) => unknown;

let globalToast: ToastFn | null = null;
const pendingToasts: UseToastOptions[] = [];

export function registerGlobalToast(toast: ToastFn | null): void {
  globalToast = toast;
  if (!toast) return;
  pendingToasts.splice(0).forEach((options) => toast(options));
}

export function showGlobalToast(options: UseToastOptions): void {
  if (typeof window === 'undefined') return;
  const merged = { ...DEFAULT_OPTIONS, ...options };
  if (globalToast) {
    globalToast(merged);
    return;
  }
  pendingToasts.push(merged);
}

export function useToastWithDeduplication() {
  const toast = useToast();
  const activeKeysRef = useRef(new Set<string>());
  const timeoutRefsRef = useRef(new Map<string, ReturnType<typeof setTimeout>>());

  return useCallback(
    (options: UseToastOptions) => {
      const key = `${options.status ?? 'info'}:${options.title ?? ''}:${options.description ?? ''}`;
      if (activeKeysRef.current.has(key)) return '';

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

      const toastId = toast({ ...DEFAULT_OPTIONS, ...options, onCloseComplete: cleanup });
      const duration = options.duration ?? DEFAULT_OPTIONS.duration ?? 5000;
      timeoutRefsRef.current.set(key, setTimeout(cleanup, duration + 300));
      return toastId;
    },
    [toast]
  );
}

/** Wires Chakra toast into non-React code paths (e.g. BaseApiService). Mount once in `_app.tsx`. */
export function GlobalToastRegistrar() {
  const toast = useToastWithDeduplication();

  useEffect(() => {
    registerGlobalToast(toast);
    return () => registerGlobalToast(null);
  }, [toast]);

  return null;
}
