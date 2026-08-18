/// <reference types="jest" />

import {
  ADOPTER_ADMIN_GUIDE_HREF,
  INSTITUTION_ADMIN_GUIDE_HREF,
  canSeeOnboardingGuide,
  getOnboardingGuideHref,
} from "../../src/config/onboardingGuide";

describe("canSeeOnboardingGuide", () => {
  it.each([
    { roles: ["ADMIN"] },
    { roles: ["MODERATOR"] },
    { roles: ["TENANT ADMIN"] },
    { roles: ["TENANT_ADMIN"] },
    { roles: ["ADMIN", "MODERATOR"] },
    { roles: ["TENANT ADMIN", "USER"] },
  ])("is true for $roles", ({ roles }) => {
    expect(canSeeOnboardingGuide(roles)).toBe(true);
  });

  it.each([
    { roles: undefined },
    { roles: [] as string[] },
    { roles: ["USER"] },
    { roles: ["GUEST"] },
    { roles: ["PROGRAM ADMIN"] },
    { roles: ["PROGRAM_ADMIN"] },
  ])("is false for $roles", ({ roles }) => {
    expect(canSeeOnboardingGuide(roles)).toBe(false);
  });
});

describe("getOnboardingGuideHref", () => {
  it.each([
    { roles: ["ADMIN"] },
    { roles: ["MODERATOR"] },
    { roles: ["admin"] },
    { roles: ["ADMIN", "TENANT ADMIN"] },
  ])("routes $roles to the Adopter Admin guide", ({ roles }) => {
    expect(getOnboardingGuideHref(roles)).toBe(ADOPTER_ADMIN_GUIDE_HREF);
  });

  it.each([
    { roles: ["TENANT ADMIN"] },
    { roles: ["TENANT_ADMIN"] },
    { roles: ["USER"] },
    { roles: ["PROGRAM ADMIN"] },
    { roles: undefined },
    { roles: [] as string[] },
  ])("routes $roles to the Institution Admin guide", ({ roles }) => {
    expect(getOnboardingGuideHref(roles)).toBe(INSTITUTION_ADMIN_GUIDE_HREF);
  });
});
