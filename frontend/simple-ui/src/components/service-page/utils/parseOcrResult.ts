// Parse OCR inference output into human-readable text and structured line data

export interface OcrWord {
  text: string;
  confidence?: number;
}

export interface OcrDisplayLine {
  text: string;
  confidence?: number;
  words: OcrWord[];
}

export interface ParsedOcrResult {
  plainText: string;
  lines: OcrDisplayLine[];
  wordCount: number;
  lineCount: number;
  averageConfidence?: number;
  isStructured: boolean;
  /** Original source string when not structured JSON */
  rawSource?: string;
}

interface OcrToken {
  text: string;
  confidence?: number;
  y: number | null;
  x: number | null;
}

function readNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function tokenPosition(item: Record<string, unknown>): { x: number | null; y: number | null } {
  const bbox = item.bbox;
  if (bbox && typeof bbox === "object") {
    const box = bbox as Record<string, unknown>;
    return {
      x: readNumber(box.x) ?? readNumber(box.left),
      y: readNumber(box.y) ?? readNumber(box.top),
    };
  }

  const polygon = item.polygon;
  if (Array.isArray(polygon) && polygon.length > 0) {
    const first = polygon[0];
    if (Array.isArray(first) && first.length >= 2) {
      return {
        x: readNumber(first[0]),
        y: readNumber(first[1]),
      };
    }
  }

  return { x: null, y: null };
}

function tokenText(item: Record<string, unknown>): string {
  const text = item.text ?? item.word ?? item.content ?? item.line;
  return typeof text === "string" ? text.trim() : "";
}

function tokenConfidence(item: Record<string, unknown>): number | undefined {
  const confidence = readNumber(item.confidence) ?? readNumber(item.score);
  if (confidence === null) return undefined;
  return confidence > 1 ? confidence / 100 : confidence;
}

function average(values: number[]): number | undefined {
  if (values.length === 0) return undefined;
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

function groupTokensIntoLines(tokens: OcrToken[]): OcrDisplayLine[] {
  if (tokens.length === 0) return [];

  const withPosition = tokens.filter((t) => t.y !== null);
  if (withPosition.length === 0) {
    const text = tokens.map((t) => t.text).join(" ").trim();
    const confidences = tokens.map((t) => t.confidence).filter((c): c is number => c !== undefined);
    return text
      ? [
          {
            text,
            confidence: average(confidences),
            words: tokens.map((t) => ({ text: t.text, confidence: t.confidence })),
          },
        ]
      : [];
  }

  const sorted = [...withPosition].sort((a, b) => {
    const yDiff = (a.y ?? 0) - (b.y ?? 0);
    if (Math.abs(yDiff) > 8) return yDiff;
    return (a.x ?? 0) - (b.x ?? 0);
  });

  const lineGroups: OcrToken[][] = [];
  let current: OcrToken[] = [];
  let currentY: number | null = null;

  for (const token of sorted) {
    if (currentY === null || Math.abs((token.y ?? 0) - currentY) <= 12) {
      current.push(token);
      currentY = currentY ?? token.y;
    } else {
      if (current.length > 0) lineGroups.push(current);
      current = [token];
      currentY = token.y;
    }
  }
  if (current.length > 0) lineGroups.push(current);

  return lineGroups
    .map((group) => {
      const words = group.map((t) => ({ text: t.text, confidence: t.confidence }));
      const confidences = words.map((w) => w.confidence).filter((c): c is number => c !== undefined);
      return {
        text: words.map((w) => w.text).join(" ").trim(),
        confidence: average(confidences),
        words,
      };
    })
    .filter((line) => line.text.length > 0);
}

function parseTextLinesArray(items: unknown[]): OcrDisplayLine[] {
  const tokens: OcrToken[] = [];

  for (const item of items) {
    if (typeof item === "string" && item.trim()) {
      tokens.push({ text: item.trim(), confidence: undefined, y: null, x: null });
      continue;
    }
    if (!item || typeof item !== "object") continue;

    const record = item as Record<string, unknown>;
    const text = tokenText(record);
    if (!text) continue;

    const { x, y } = tokenPosition(record);
    tokens.push({
      text,
      confidence: tokenConfidence(record),
      x,
      y,
    });
  }

  return groupTokensIntoLines(tokens);
}

function extractTextLines(payload: Record<string, unknown>): unknown[] | null {
  const candidates = [
    payload.text_lines,
    payload.textLines,
    payload.lines,
    payload.words,
    payload.results,
  ];

  for (const candidate of candidates) {
    if (Array.isArray(candidate) && candidate.length > 0) {
      return candidate;
    }
  }

  return null;
}

function parseStructuredPayload(payload: Record<string, unknown>): ParsedOcrResult | null {
  const textLines = extractTextLines(payload);
  if (textLines) {
    const lines = parseTextLinesArray(textLines);
    const plainText = lines.map((line) => line.text).join("\n").trim();
    const allConfidences = lines
      .map((line) => line.confidence)
      .filter((c): c is number => c !== undefined);

    return {
      plainText,
      lines,
      wordCount: lines.reduce((count, line) => count + line.words.length, 0),
      lineCount: lines.length,
      averageConfidence: average(allConfidences),
      isStructured: true,
    };
  }

  const plainCandidates = [payload.text, payload.full_text, payload.fullText];
  const plain = plainCandidates.find((value): value is string => typeof value === "string" && value.trim().length > 0);

  if (plain) {
    const trimmed = plain.trim();
    return {
      plainText: trimmed,
      lines: [{ text: trimmed, words: [{ text: trimmed }] }],
      wordCount: trimmed.split(/\s+/).filter(Boolean).length,
      lineCount: 1,
      isStructured: true,
    };
  }

  return null;
}

/**
 * Turn OCR `output[0].source` (or full inference response) into display-friendly data.
 */
export function parseOcrSource(source: string | Record<string, unknown> | null | undefined): ParsedOcrResult {
  if (!source) {
    return {
      plainText: "",
      lines: [],
      wordCount: 0,
      lineCount: 0,
      isStructured: false,
    };
  }

  if (typeof source === "object") {
    const fromOutput = Array.isArray((source as { output?: unknown[] }).output)
      ? parseOcrSource(
          ((source as { output: { source?: string }[] }).output[0]?.source as string) ?? ""
        )
      : null;
    if (fromOutput && fromOutput.plainText) return fromOutput;

    const structured = parseStructuredPayload(source as Record<string, unknown>);
    if (structured) return structured;
  }

  const raw = typeof source === "string" ? source.trim() : "";
  if (!raw) {
    return {
      plainText: "",
      lines: [],
      wordCount: 0,
      lineCount: 0,
      isStructured: false,
    };
  }

  if (raw.startsWith("{") || raw.startsWith("[")) {
    try {
      const parsed = JSON.parse(raw) as Record<string, unknown>;
      const structured = parseStructuredPayload(parsed);
      if (structured) {
        return { ...structured, rawSource: raw };
      }
    } catch {
      // fall through to plain text
    }
  }

  const lines = raw.split(/\n/).filter((line) => line.trim().length > 0);
  return {
    plainText: raw,
    lines: lines.map((text) => ({ text, words: [{ text }] })),
    wordCount: raw.split(/\s+/).filter(Boolean).length,
    lineCount: lines.length || (raw ? 1 : 0),
    isStructured: false,
    rawSource: raw,
  };
}

export function formatConfidence(confidence?: number): string {
  if (confidence === undefined) return "—";
  const pct = confidence <= 1 ? confidence * 100 : confidence;
  return `${pct.toFixed(0)}%`;
}

export function confidenceColor(confidence?: number): string {
  if (confidence === undefined) return "gray";
  const pct = confidence <= 1 ? confidence * 100 : confidence;
  if (pct >= 90) return "green";
  if (pct >= 75) return "yellow";
  return "orange";
}
