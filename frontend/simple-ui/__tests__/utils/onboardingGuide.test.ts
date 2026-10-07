/// <reference types="jest" />

import {
  ADOPTER_ADMIN_GUIDE_HREF,
  INSTITUTION_ADMIN_GUIDE_HREF,
  PRE_LOGIN_GUIDE_OPTIONS,
  canSeeOnboardingGuide,
  getOnboardingGuideHref,
  getPreLoginGuideOptions,
} from "../../src/config/onboardingGuide";

describe("PRE_LOGIN_GUIDE_OPTIONS", () => {
  it("exposes both guide paths for the signed-out chooser", () => {
    expect(PRE_LOGIN_GUIDE_OPTIONS.map((option) => option.href)).toEqual([
      ADOPTER_ADMIN_GUIDE_HREF,
      INSTITUTION_ADMIN_GUIDE_HREF,
    ]);
  });
});

describe("getPreLoginGuideOptions", () => {
  it("returns both guides without a platform name query", () => {
    expect(getPreLoginGuideOptions()).toEqual([
      { label: "Adopter Admin Guide", href: ADOPTER_ADMIN_GUIDE_HREF },
      { label: "Institution Admin Guide", href: INSTITUTION_ADMIN_GUIDE_HREF },
    ]);
  });
});

describe("canSeeOnboardingGuide", () => {
  it.each([
    { roles: ["ADMIN"] },
    { roles: ["TENANT ADMIN"] },
    { roles: ["TENANT_ADMIN"] },
    { roles: ["ADMIN", "MODERATOR"] },
    { roles: ["TENANT ADMIN", "MODERATOR"] },
    { roles: ["TENANT ADMIN", "USER"] },
  ])("is true for $roles", ({ roles }) => {
    expect(canSeeOnboardingGuide(roles)).toBe(true);
  });

  it.each([
    { roles: undefined },
    { roles: [] as string[] },
    { roles: ["MODERATOR"] },
    { roles: ["USER"] },
    { roles: ["GUEST"] },
    { roles: ["USAGE VIEWER"] },
    { roles: ["USAGE_VIEWER"] },
  ])("is false for $roles", ({ roles }) => {
    expect(canSeeOnboardingGuide(roles)).toBe(false);
  });
});

describe("getOnboardingGuideHref", () => {
  it.each([
    { roles: ["ADMIN"] },
    { roles: ["admin"] },
    { roles: ["ADMIN", "TENANT ADMIN"] },
  ])("routes $roles to the Adopter Admin guide", ({ roles }) => {
    expect(getOnboardingGuideHref(roles)).toBe(ADOPTER_ADMIN_GUIDE_HREF);
  });

  it.each([
    { roles: ["MODERATOR"] },
    { roles: ["TENANT ADMIN"] },
    { roles: ["TENANT_ADMIN"] },
    { roles: ["USER"] },
    { roles: ["USAGE VIEWER"] },
    { roles: undefined },
    { roles: [] as string[] },
  ])("routes $roles to the Institution Admin guide", ({ roles }) => {
    expect(getOnboardingGuideHref(roles)).toBe(INSTITUTION_ADMIN_GUIDE_HREF);
  });
});
