/**
 * Removes `//` line comments and block comments from JSONC text so it parses as strict JSON.
 *
 * Scanning is string-aware: comment markers inside string values (URLs such as
 * `https://example.com`, or literal text like `/* … *\/`) are preserved. Trailing commas
 * left dangling once a comment is removed are dropped, so a partially edited file still parses.
 *
 * Used for the annotated sample model JSON, which ships with explanatory comments that
 * users keep while editing and which must be stripped before upload.
 */
export function stripJsonComments(text: string): string {
  let out = "";
  let inString = false;
  let inLineComment = false;
  let inBlockComment = false;

  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    const next = text[i + 1];

    if (inLineComment) {
      if (char === "\n") {
        inLineComment = false;
        out += char;
      }
      continue;
    }

    if (inBlockComment) {
      if (char === "*" && next === "/") {
        inBlockComment = false;
        i++;
      }
      continue;
    }

    if (inString) {
      out += char;
      if (char === "\\") {
        // Preserve the escaped character verbatim so quotes inside strings don't end it early
        out += next ?? "";
        i++;
      } else if (char === '"') {
        inString = false;
      }
      continue;
    }

    if (char === '"') {
      inString = true;
      out += char;
      continue;
    }

    if (char === "/" && next === "/") {
      inLineComment = true;
      i++;
      continue;
    }

    if (char === "/" && next === "*") {
      inBlockComment = true;
      i++;
      continue;
    }

    // A removed comment can leave a dangling comma before a closing brace/bracket
    if (char === "}" || char === "]") {
      out = out.replace(/,\s*$/, "");
    }

    out += char;
  }

  return out;
}
