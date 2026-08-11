/** Retry a fetch until `isReady`, or attempts are exhausted. */
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
