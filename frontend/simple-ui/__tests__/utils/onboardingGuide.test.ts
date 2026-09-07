/// <reference types="jest" />

import {
  ADOPTER_ADMIN_GUIDE_HREF,
  INSTITUTION_ADMIN_GUIDE_HREF,
  ONBOARDING_GUIDE_PLATFORM_NAME_PARAM,
  PRE_LOGIN_GUIDE_OPTIONS,
  canSeeOnboardingGuide,
  getOnboardingGuideHref,
  getPreLoginGuideOptions,
  withPlatformNameQuery,
} from "../../src/config/onboardingGuide";
import { applyRuntimeConfig, EMPTY_RUNTIME_CONFIG } from "../../src/config/runtimeConfig";

describe("PRE_LOGIN_GUIDE_OPTIONS", () => {
  it("exposes both guide paths for the signed-out chooser", () => {
    expect(PRE_LOGIN_GUIDE_OPTIONS.map((option) => option.href)).toEqual([
      ADOPTER_ADMIN_GUIDE_HREF,
      INSTITUTION_ADMIN_GUIDE_HREF,
    ]);
  });
});

describe("withPlatformNameQuery", () => {
  it("appends platformName from runtime config by default", () => {
    applyRuntimeConfig({ ...EMPTY_RUNTIME_CONFIG, platformName: "Acme AI" });
    expect(withPlatformNameQuery(ADOPTER_ADMIN_GUIDE_HREF)).toBe(
      `${ADOPTER_ADMIN_GUIDE_HREF}?${ONBOARDING_GUIDE_PLATFORM_NAME_PARAM}=Acme%20AI`,
    );
  });

  it("encodes special characters in the platform name", () => {
    expect(withPlatformNameQuery(INSTITUTION_ADMIN_GUIDE_HREF, "A&B")).toBe(
      `${INSTITUTION_ADMIN_GUIDE_HREF}?${ONBOARDING_GUIDE_PLATFORM_NAME_PARAM}=A%26B`,
    );
  });
});

describe("getPreLoginGuideOptions", () => {
  it("returns both guides with platformName query", () => {
    const options = getPreLoginGuideOptions("Custom Portal");
    expect(options).toEqual([
      {
        label: "Adopter Admin Guide",
        href: withPlatformNameQuery(ADOPTER_ADMIN_GUIDE_HREF, "Custom Portal"),
      },
      {
        label: "Institution Admin Guide",
        href: withPlatformNameQuery(INSTITUTION_ADMIN_GUIDE_HREF, "Custom Portal"),
      },
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
  const brand = "Test Brand";

  it.each([
    { roles: ["ADMIN"] },
    { roles: ["MODERATOR"] },
    { roles: ["admin"] },
    { roles: ["ADMIN", "TENANT ADMIN"] },
  ])("routes $roles to the Adopter Admin guide with platformName", ({ roles }) => {
    expect(getOnboardingGuideHref(roles, brand)).toBe(
      withPlatformNameQuery(ADOPTER_ADMIN_GUIDE_HREF, brand),
    );
  });

  it.each([
    { roles: ["TENANT ADMIN"] },
    { roles: ["TENANT_ADMIN"] },
    { roles: ["USER"] },
    { roles: ["USAGE VIEWER"] },
    { roles: undefined },
    { roles: [] as string[] },
  ])("routes $roles to the Institution Admin guide with platformName", ({ roles }) => {
    expect(getOnboardingGuideHref(roles, brand)).toBe(
      withPlatformNameQuery(INSTITUTION_ADMIN_GUIDE_HREF, brand),
    );
  });
});
