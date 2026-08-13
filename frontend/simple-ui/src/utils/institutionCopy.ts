/**
 * Single place to change tenant → Institution display copy.
 *
 * Applied automatically by toast, parseError, confirmCopy, and shared chrome
 * (sidebar, header, tables, confirm/modal headers).
 *
 * Do not use on API matching, URLs, IDs, or request payloads.
 */

function matchWordCase(sample: string, replacement: string): string {
  if (sample === sample.toUpperCase()) return replacement.toUpperCase();
  if (sample[0] === sample[0].toUpperCase()) {
    return replacement[0].toUpperCase() + replacement.slice(1);
  }
  return replacement;
}

/** Rewrite tenant terminology in a display string. Idempotent. */
export function formatInstitutionCopy(value: string | null | undefined): string {
  if (value == null || value === "") return value ?? "";

  return value
    .replace(/\b([Aa])n?\s+(TENANTS?|Tenants?|tenants?)\b/g, (_m, article: string, noun: string) => {
      const isPlural = /s$/i.test(noun);
      const inst = matchWordCase(noun, isPlural ? "institutions" : "institution");
      const an = article === article.toUpperCase() ? "AN" : article === "A" ? "An" : "an";
      return `${an} ${inst}`;
    })
    .replace(/\btenant_ids\b/gi, (m) => matchWordCase(m, "institution IDs"))
    .replace(/\btenant_id\b/gi, (m) => matchWordCase(m, "institution ID"))
    .replace(/\bTENANTS\b/g, "INSTITUTIONS")
    .replace(/\bTenants\b/g, "Institutions")
    .replace(/\btenants\b/g, "institutions")
    .replace(/\bTENANT\b/g, "INSTITUTION")
    .replace(/\bTenant\b/g, "Institution")
    .replace(/\btenant\b/g, "institution");
}

/** Native confirm dialog with institution copy applied. */
export function confirmCopy(message: string): boolean {
  if (typeof window === "undefined") return false;
  return window.confirm(formatInstitutionCopy(message));
}
