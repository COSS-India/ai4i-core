export type OCRParseResult =
  | { ok: true; text: string }
  | { ok: false; error: string };

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

export function cleanOCRText(text: string): string {
  return text
    .replace(/<br\s*\/?>/gi, "\n")
    .split("\n")
    .map((line) => line.trimEnd())
    .join("\n")
    .trim();
}

function fromObject(parsed: Record<string, unknown>): OCRParseResult {
  if (parsed.success === false) return { ok: false, error: "OCR processing failed." };

  let text = typeof parsed.full_text === "string" ? cleanOCRText(parsed.full_text) : "";
  if (!text && Array.isArray(parsed.text_lines)) {
    text = cleanOCRText(
      parsed.text_lines
        .filter(isRecord)
        .map((line) => (typeof line.text === "string" ? line.text : ""))
        .filter(Boolean)
        .join("\n")
    );
  }
  return text
    ? { ok: true, text }
    : { ok: false, error: "Unable to extract readable text from the uploaded image." };
}

export function parseOCRResponse(source: unknown): OCRParseResult {
  if (source == null || (typeof source === "string" && !source.trim())) {
    return { ok: false, error: "No OCR response data." };
  }
  if (isRecord(source)) return fromObject(source);

  if (typeof source !== "string") {
    return { ok: false, error: "Unable to parse OCR response." };
  }

  try {
    const parsed = JSON.parse(source.trim());
    return isRecord(parsed) ? fromObject(parsed) : { ok: false, error: "Unable to parse OCR response." };
  } catch {
    const text = cleanOCRText(source.trim());
    return text ? { ok: true, text } : { ok: false, error: "Unable to parse OCR response." };
  }
}
