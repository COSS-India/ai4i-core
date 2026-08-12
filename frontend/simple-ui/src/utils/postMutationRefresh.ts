/**
 * Retry a read until `isReady`, or attempts are exhausted.
 * Callers must keep `run` free of React state commits — apply the returned
 * value once (when ready or after the last attempt) to avoid optimistic-row
 * flicker and loading-spinner flashes between polls.
 */
export async function refreshUntil<T>(
  run: () => Promise<T>,
  isReady: (data: T) => boolean,
  attempts = 4,
  delayMs = 300,
): Promise<T> {
  let last = await run();
  for (let i = 1; i < attempts && !isReady(last); i++) {
    await new Promise((r) => setTimeout(r, delayMs));
    last = await run();
  }
  return last;
}
