import type { ErrorInfo } from "./types";

export function parseValidationErrors(detail: unknown[]): ErrorInfo | null {
  const errorMessages = detail
    .filter((err): err is { msg?: string; loc?: unknown[] } => typeof err === "object" && err !== null)
    .filter((err) => err.msg)
    .map((err) => {
      let msg = String(err.msg);
      if (msg.startsWith("Value error, ")) {
        msg = msg.substring("Value error, ".length);
      }
      if (err.loc && Array.isArray(err.loc) && err.loc.length > 0) {
        const fieldPath = err.loc.slice(1).join(".");
        return `${fieldPath ? `${fieldPath}: ` : ""}${msg}`;
      }
      return msg;
    });

  if (errorMessages.length === 0) return null;

  return {
    title: "Validation Error",
    message: errorMessages.join("; "),
    showOnlyMessage: true,
  };
}

export function parseNestedDetailMessage(rawMessage: string): string {
  if (!rawMessage.trim().startsWith("{") && !rawMessage.trim().startsWith("[")) {
    return rawMessage;
  }

  try {
    const jsonLike = rawMessage.replace(/'/g, '"');
    const parsed = JSON.parse(jsonLike) as { message?: string; error?: string };
    if (parsed?.message) return String(parsed.message);
    if (parsed?.error) return String(parsed.error);
  } catch {
    const messageMatch = rawMessage.match(/['"]message['"]\s{0,5}:\s{0,5}['"]([^'"]+)['"]/);
    if (messageMatch?.[1]) return messageMatch[1];
  }

  return rawMessage;
}
