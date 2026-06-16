// Custom hook that wraps Chakra UI's useToast with deduplication logic
// Prevents showing the same toast message multiple times until the previous one disappears

import { useToast, UseToastOptions } from '@chakra-ui/react';
import { useRef, useCallback } from 'react';

/**
 * Generates a unique key for a toast based on its content
 */
function getToastKey(options: UseToastOptions): string {
  const title = options.title || '';
  const description = options.description || '';
  const status = options.status || 'info';
  return `${status}:${title}:${description}`;
}

/**
 * Custom hook that wraps useToast with deduplication logic
 * If the same toast (same title, description, and status) is shown,
 * it won't be displayed again until the previous one disappears
 */
export function useToastWithDeduplication() {
  const toast = useToast();
  const activeToastsRef = useRef<Set<string>>(new Set());
  const timeoutRefsRef = useRef<Map<string, NodeJS.Timeout>>(new Map());

  const showToast = useCallback((options: UseToastOptions) => {
    const key = getToastKey(options);

    // If this toast is already active, don't show it again
    if (activeToastsRef.current.has(key)) {
      return;
    }

    // Mark this toast as active
    activeToastsRef.current.add(key);

    // Store original onCloseComplete callback
    const originalOnCloseComplete = options.onCloseComplete;

    // Create cleanup function
    const cleanup = () => {
      activeToastsRef.current.delete(key);
      const timeoutId = timeoutRefsRef.current.get(key);
      if (timeoutId) {
        clearTimeout(timeoutId);
        timeoutRefsRef.current.delete(key);
      }
      if (originalOnCloseComplete) {
        originalOnCloseComplete();
      }
    };

    // Show the toast with onCloseComplete callback to remove from active set
    const toastId = toast({
      ...options,
      onCloseComplete: cleanup,
    });

    // Also set a timeout based on duration as a fallback (in case onCloseComplete doesn't fire)
    const duration = options.duration ?? 5000; // Default Chakra UI duration
    const timeoutId = setTimeout(() => {
      cleanup();
    }, duration);
    timeoutRefsRef.current.set(key, timeoutId);

    return toastId;
  }, [toast]);

  return showToast;
}
