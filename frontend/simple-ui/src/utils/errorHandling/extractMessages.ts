/**
 * Recursively extract human-readable messages from arbitrary API error payloads.
 * Never throws — returns an empty array when nothing readable is found.
 */

const MESSAGE_KEYS = ['message', 'error', 'detail', 'title', 'description', 'error_msg', 'msg'] as const;

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function cleanPydanticMessage(msg: string): string {
  if (msg.startsWith('Value error, ')) {
    return msg.substring('Value error, '.length);
  }
  return msg;
}

function formatPydanticItem(item: Record<string, unknown>): string | null {
  if (typeof item.msg === 'string') {
    let message = cleanPydanticMessage(item.msg);
    if (Array.isArray(item.loc) && item.loc.length > 0) {
      const fieldPath = item.loc.slice(1).join('.');
      if (fieldPath) {
        message = `${fieldPath}: ${message}`;
      }
    }
    return message;
  }
  return extractMessagesFromValue(item)[0] ?? null;
}

function tryParseDictLikeString(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) {
    return null;
  }

  try {
    const jsonLike = trimmed.replaceAll("'", '"');
    const parsed = JSON.parse(jsonLike) as unknown;
    const messages = extractMessagesFromValue(parsed);
    return messages[0] ?? null;
  } catch {
    const messageMatch = trimmed.match(/['"]message['"]\s{0,5}:\s{0,5}['"]([^'"]+)['"]/);
    if (messageMatch?.[1]) {
      return messageMatch[1];
    }
  }

  return null;
}

function stringFromValue(value: unknown): string | null {
  if (value == null) return null;
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) return null;
    const nested = tryParseDictLikeString(trimmed);
    return nested ?? trimmed;
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  return null;
}

export function extractMessagesFromValue(value: unknown, depth = 0): string[] {
  if (depth > 8) return [];

  const asString = stringFromValue(value);
  if (asString) return [asString];

  if (Array.isArray(value)) {
    const messages: string[] = [];
    value.forEach((item) => {
      if (typeof item === 'string') {
        const msg = stringFromValue(item);
        if (msg) messages.push(msg);
        return;
      }
      if (isPlainObject(item)) {
        const pydantic = formatPydanticItem(item);
        if (pydantic) {
          messages.push(pydantic);
          return;
        }
        if (typeof item.message === 'string') {
          messages.push(item.message);
          return;
        }
      }
      messages.push(...extractMessagesFromValue(item, depth + 1));
    });
    return messages;
  }

  if (!isPlainObject(value)) return [];

  const messages: string[] = [];

  if (Array.isArray(value.errors)) {
    messages.push(...extractMessagesFromValue(value.errors, depth + 1));
  }

  for (const key of MESSAGE_KEYS) {
    if (key in value) {
      const extracted = extractMessagesFromValue(value[key], depth + 1);
      messages.push(...extracted);
    }
  }

  if (isPlainObject(value.data)) {
    messages.push(...extractMessagesFromValue(value.data, depth + 1));
  }

  if (messages.length === 0) {
    for (const nested of Object.values(value)) {
      if (nested === value.errors || nested === value.data) continue;
      const extracted = extractMessagesFromValue(nested, depth + 1);
      if (extracted.length > 0) {
        messages.push(...extracted);
        break;
      }
    }
  }

  return messages;
}

export function combineMessages(messages: string[]): string {
  const unique = Array.from(new Set(messages.map((m) => m.trim()).filter(Boolean)));
  return unique.join('; ');
}
