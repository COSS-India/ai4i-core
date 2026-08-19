/**
 * Same-origin onboarding guides. Served as text/html with
 * Content-Disposition: inline so the browser views them instead of downloading.
 */
import {
  isAdopterAdminUser,
  isDefaultAdminUser,
  isTenantAdminUser,
} from "../utils/rbac";

export const INSTITUTION_ADMIN_GUIDE_HREF =
  "/onboarding-guide/institution-admin-guide.html";
export const ADOPTER_ADMIN_GUIDE_HREF =
  "/onboarding-guide/adopter-admin-guide.html";

/** Signed-out home page uses the Institution Admin guide. */
export const ONBOARDING_GUIDE_HREF = INSTITUTION_ADMIN_GUIDE_HREF;

export function canSeeOnboardingGuide(roles?: string[]): boolean {
  // Moderator (Adopter Admin without platform ADMIN) does not see the guide.
  if (isAdopterAdminUser(roles)) return false;
  return isDefaultAdminUser(roles) || isTenantAdminUser(roles);
}

/** Platform ADMIN gets the Adopter guide; Institution Admin gets theirs. */
export function getOnboardingGuideHref(roles?: string[]): string {
  if (isDefaultAdminUser(roles)) {
    return ADOPTER_ADMIN_GUIDE_HREF;
  }
  return INSTITUTION_ADMIN_GUIDE_HREF;
}
