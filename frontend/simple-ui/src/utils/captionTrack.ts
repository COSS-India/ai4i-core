// WebVTT caption track helpers for accessible audio playback

/** Format seconds as a WebVTT timestamp (HH:MM:SS.mmm). */
export function formatVttTimestamp(seconds: number): string {
  const safeSeconds = Number.isFinite(seconds) && seconds > 0 ? seconds : 3600;
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const secs = safeSeconds % 60;
  const wholeSecs = Math.floor(secs);
  const millis = Math.round((secs - wholeSecs) * 1000);

  return (
    `${String(hours).padStart(2, '0')}:` +
    `${String(minutes).padStart(2, '0')}:` +
    `${String(wholeSecs).padStart(2, '0')}.` +
    `${String(millis).padStart(3, '0')}`
  );
}

/** Build a single-cue WebVTT document for plain-text captions. */
export function buildWebVttDocument(text: string, durationSeconds?: number): string {
  const cueText = text.replaceAll(/\r\n/g, '\n').replaceAll(/\r/g, '\n').trim();
  const end = formatVttTimestamp(durationSeconds ?? 3600);
  return `WEBVTT\n\n00:00:00.000 --> ${end}\n${cueText}\n`;
}

/** Create an object URL for a WebVTT caption track. Caller must revoke when done. */
export function createCaptionTrackBlobUrl(
  text: string,
  durationSeconds?: number
): string {
  const vtt = buildWebVttDocument(text, durationSeconds);
  const blob = new Blob([vtt], { type: 'text/vtt' });
  return URL.createObjectURL(blob);
}
