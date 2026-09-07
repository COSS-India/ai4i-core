/**
 * Same-origin onboarding guides. Served as text/html with
 * Content-Disposition: inline so the browser views them instead of downloading.
 *
 * PLATFORM_NAME is passed as ?platformName= so the static HTML can rebrand
 * without a rebuild (see public/assests/onboarding-guide/*.html).
 */
import { DEFAULT_PLATFORM_NAME } from "./branding";
import { getPlatformName } from "./runtimeConfig";
import { isDefaultAdminUser, isTenantAdminUser } from "../utils/rbac";

export const INSTITUTION_ADMIN_GUIDE_HREF =
  "/assests/onboarding-guide/institution-admin-guide.html";
export const ADOPTER_ADMIN_GUIDE_HREF =
  "/assests/onboarding-guide/adopter-admin-guide.html";

/** Query key read by the guide pages' inline branding script. */
export const ONBOARDING_GUIDE_PLATFORM_NAME_PARAM = "platformName";

/** Default brand string baked into the static HTML (fallback when param absent). */
export const ONBOARDING_GUIDE_DEFAULT_PLATFORM_NAME = DEFAULT_PLATFORM_NAME;

/** Append runtime PLATFORM_NAME so the opened guide can swap the baked default. */
export function withPlatformNameQuery(
  href: string,
  platformName: string = getPlatformName(),
): string {
  const name = (platformName ?? "").trim() || DEFAULT_PLATFORM_NAME;
  const url = new URL(href, "http://onboarding.local");
  url.searchParams.set(ONBOARDING_GUIDE_PLATFORM_NAME_PARAM, name);
  return `${url.pathname}${url.search}`;
}

/** Signed-out home: both guides, so users can orient before their account is active. */
export const PRE_LOGIN_GUIDE_OPTIONS = [
  { label: "Adopter Admin Guide", href: ADOPTER_ADMIN_GUIDE_HREF },
  { label: "Institution Admin Guide", href: INSTITUTION_ADMIN_GUIDE_HREF },
] as const;

/** Pre-login chooser hrefs with the current PLATFORM_NAME query. */
export function getPreLoginGuideOptions(
  platformName: string = getPlatformName(),
): { label: string; href: string }[] {
  return PRE_LOGIN_GUIDE_OPTIONS.map((option) => ({
    label: option.label,
    href: withPlatformNameQuery(option.href, platformName),
  }));
}

/** Platform ADMIN and Tenant Admin only; plain MODERATOR (no TENANT ADMIN) is excluded. */
export function canSeeOnboardingGuide(roles?: string[]): boolean {
  return isDefaultAdminUser(roles) || isTenantAdminUser(roles);
}

/** Platform ADMIN gets the Adopter guide; Institution Admin gets theirs. */
export function getOnboardingGuideHref(
  roles?: string[],
  platformName: string = getPlatformName(),
): string {
  const path = isDefaultAdminUser(roles)
    ? ADOPTER_ADMIN_GUIDE_HREF
    : INSTITUTION_ADMIN_GUIDE_HREF;
  return withPlatformNameQuery(path, platformName);
}
