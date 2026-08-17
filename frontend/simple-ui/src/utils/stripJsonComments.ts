/**
 * Removes `//` line comments and block comments from JSONC text so it parses as strict JSON.
 *
 * Scanning is string-aware: comment markers inside string values (URLs such as
 * `https://example.com`, or literal text like `/* … *\/`) are preserved. Trailing commas
 * left dangling once a comment is removed are dropped, so a partially edited file still parses.
 *
 * Line breaks are always preserved, including inside removed comments, so the line and column
 * that `JSON.parse` reports on failure point at the matching line of the user's own file.
 *
 * Used for the annotated sample model JSON, which ships with explanatory comments that
 * users keep while editing and which must be stripped before upload.
 */
export function stripJsonComments(text: string): string {
  // Characters accumulate one per slot so the tail can be trimmed in place. Rescanning a
  // growing string on every closing bracket would make this quadratic in the input size.
  const out: string[] = [];
  let inString = false;
  let inLineComment = false;
  let inBlockComment = false;

  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    const next = text[i + 1];

    if (inLineComment) {
      if (char === "\n") {
        inLineComment = false;
        out.push(char);
      }
      continue;
    }

    if (inBlockComment) {
      if (char === "*" && next === "/") {
        inBlockComment = false;
        i++;
      } else if (char === "\n") {
        // Keep the line break so positions reported by JSON.parse match the user's file
        out.push(char);
      }
      continue;
    }

    if (inString) {
      out.push(char);
      if (char === "\\") {
        // Preserve the escaped character verbatim so quotes inside strings don't end it early
        if (next !== undefined) {
          out.push(next);
        }
        i++;
      } else if (char === '"') {
        inString = false;
      }
      continue;
    }

    if (char === '"') {
      inString = true;
      out.push(char);
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

    // A removed comment can leave a dangling comma before a closing brace/bracket. Walk back
    // over the trailing whitespace only — each slot is visited at most once per bracket.
    if (char === "}" || char === "]") {
      let end = out.length;
      while (end > 0 && /\s/.test(out[end - 1])) {
        end--;
      }
      if (end > 0 && out[end - 1] === ",") {
        // Blank the comma rather than truncating, so the line breaks after it survive
        out[end - 1] = "";
      }
    }

    out.push(char);
  }

  return out.join("");
}
