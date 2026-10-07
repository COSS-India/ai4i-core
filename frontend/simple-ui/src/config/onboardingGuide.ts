/**
 * Same-origin onboarding guides. Served as text/html with
 * Content-Disposition: inline so the browser views them instead of downloading.
 *
 * The guide pages read PLATFORM_NAME from same-origin /api/config on load
 * (deployment env) and swap the baked-in default. The name is not taken
 * from the URL.
 */
import { isDefaultAdminUser, isTenantAdminUser } from "../utils/rbac";

export const INSTITUTION_ADMIN_GUIDE_HREF =
  "/assests/onboarding-guide/institution-admin-guide.html";
export const ADOPTER_ADMIN_GUIDE_HREF =
  "/assests/onboarding-guide/adopter-admin-guide.html";

/** Signed-out home: both guides, so users can orient before their account is active. */
export const PRE_LOGIN_GUIDE_OPTIONS = [
  { label: "Adopter Admin Guide", href: ADOPTER_ADMIN_GUIDE_HREF },
  { label: "Institution Admin Guide", href: INSTITUTION_ADMIN_GUIDE_HREF },
] as const;

/** Pre-login chooser hrefs. Branding is applied by the guide pages themselves. */
export function getPreLoginGuideOptions(): { label: string; href: string }[] {
  return PRE_LOGIN_GUIDE_OPTIONS.map((option) => ({
    label: option.label,
    href: option.href,
  }));
}

/** Platform ADMIN and Tenant Admin only; plain MODERATOR (no TENANT ADMIN) is excluded. */
export function canSeeOnboardingGuide(roles?: string[]): boolean {
  return isDefaultAdminUser(roles) || isTenantAdminUser(roles);
}

/** Platform ADMIN gets the Adopter guide; Institution Admin gets theirs. */
export function getOnboardingGuideHref(roles?: string[]): string {
  return isDefaultAdminUser(roles)
    ? ADOPTER_ADMIN_GUIDE_HREF
    : INSTITUTION_ADMIN_GUIDE_HREF;
}
