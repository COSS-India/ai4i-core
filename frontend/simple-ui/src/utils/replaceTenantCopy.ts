import {
  INSTITUTION,
  INSTITUTIONS,
  INSTITUTION_ARTICLE,
  INSTITUTION_ARTICLE_CAP,
} from "../config/constants";

/** If copy still says tenant/tenants (e.g. BE), show INSTITUTION / INSTITUTIONS instead. */
export function replaceTenantCopy(value: string | null | undefined): string {
  if (value == null || value === "") return value ?? "";
  const next = String(value).replace(/\btenants?\b/gi, (match) => {
    const replacement = match.toLowerCase() === "tenants" ? INSTITUTIONS : INSTITUTION;
    if (match === match.toUpperCase()) return replacement.toUpperCase();
    if (match[0] === match[0].toUpperCase()) {
      return replacement[0].toUpperCase() + replacement.slice(1).toLowerCase();
    }
    return replacement.toLowerCase();
  });
  if (INSTITUTION_ARTICLE !== "an") return next;
  const alts = [INSTITUTION, INSTITUTIONS, INSTITUTION.toLowerCase(), INSTITUTIONS.toLowerCase()]
    .filter((v, i, a) => a.indexOf(v) === i)
    .map((s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("|");
  return next
    .replace(new RegExp(`\\bA(\\s+)(${alts})\\b`, "g"), `${INSTITUTION_ARTICLE_CAP}$1$2`)
    .replace(new RegExp(`\\ba(\\s+)(${alts})\\b`, "g"), `${INSTITUTION_ARTICLE}$1$2`);
}
