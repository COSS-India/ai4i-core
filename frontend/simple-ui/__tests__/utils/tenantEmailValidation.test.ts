import {
  EMAIL_ALREADY_EXISTS_MSG,
  EMAIL_INVALID_FORMAT_MSG,
  EMAIL_USER_ALREADY_EXISTS_MSG,
  collectInstitutionAdminEmails,
  collectInstitutionUserEmails,
  emailSetHas,
  isTenantContactEmailEditable,
  normalizeEmail,
  resolveTenantEmailUpdateFeedback,
  validateTenantContactEmail,
} from "../../src/utils/tenantEmailValidation";
import { INSTITUTION, TENANT } from "../../src/config/constants";
import type { TenantUserView } from "../../src/types/tenant";

function user(
  email: string,
  roles: string[] = ["USER"],
): TenantUserView {
  return {
    user_id: email,
    username: email.split("@")[0] ?? "u",
    email,
    is_active: true,
    roles,
  };
}

describe("collectInstitutionAdminEmails (AI4IDS-3401)", () => {
  it("collects only TENANT ADMIN emails, normalized", () => {
    const emails = collectInstitutionAdminEmails([
      user("Admin@Example.com", ["TENANT ADMIN"]),
      user("user@example.com", ["USER"]),
      user("both@example.com", ["USER", "TENANT ADMIN"]),
    ]);
    expect(emails).toEqual(
      new Set(["admin@example.com", "both@example.com"]),
    );
  });
});

describe("collectInstitutionUserEmails", () => {
  it("collects every provisioned user email", () => {
    expect(
      collectInstitutionUserEmails([
        { email: "A@x.com" },
        { email: "b@x.com" },
        { email: "  " },
      ]),
    ).toEqual(new Set(["a@x.com", "b@x.com"]));
  });
});

describe("isTenantContactEmailEditable (AI4IDS-3401)", () => {
  it("allows PENDING and ACTIVE only", () => {
    expect(isTenantContactEmailEditable(TENANT.STATUS.PENDING)).toBe(true);
    expect(isTenantContactEmailEditable(TENANT.STATUS.ACTIVE)).toBe(true);
    expect(isTenantContactEmailEditable(TENANT.STATUS.SUSPENDED)).toBe(false);
    expect(isTenantContactEmailEditable(TENANT.STATUS.DEACTIVATED)).toBe(false);
    expect(isTenantContactEmailEditable(undefined)).toBe(false);
  });
});

describe("resolveTenantEmailUpdateFeedback (AI4IDS-3401)", () => {
  it("uses verification toast when pending_email is set and verification was sent", () => {
    expect(
      resolveTenantEmailUpdateFeedback(
        {
          email: "old@acme.com",
          pending_email: "new@acme.com",
          email_verification_sent: true,
          status: TENANT.STATUS.ACTIVE,
        },
        "old@acme.com",
      ),
    ).toEqual({
      toastType: "info",
      message:
        "Verification email sent to the new address. The change takes effect once it's verified.",
      email: "old@acme.com",
      pending_email: "new@acme.com",
    });
  });

  it("uses activation-link toast for PENDING institution reissue", () => {
    expect(
      resolveTenantEmailUpdateFeedback(
        {
          email: "new@acme.com",
          pending_email: null,
          email_verification_sent: true,
          status: TENANT.STATUS.PENDING,
        },
        "old@acme.com",
      ),
    ).toEqual({
      toastType: "info",
      message:
        "Email updated. A new activation link was sent to the new address.",
      email: "new@acme.com",
      pending_email: null,
    });
  });

  it("applies immediately when already an Institution Admin (no pending, no send)", () => {
    expect(
      resolveTenantEmailUpdateFeedback(
        {
          email: "admin@acme.com",
          pending_email: null,
          email_verification_sent: false,
          status: TENANT.STATUS.ACTIVE,
        },
        "old@acme.com",
      ),
    ).toEqual({
      toastType: "success",
      message: `${INSTITUTION} updated.`,
      email: "admin@acme.com",
      pending_email: null,
    });
  });
});

describe("validateTenantContactEmail with allowedUserEmails (AI4IDS-3401)", () => {
  const tenantEmails = new Set(["other-tenant@example.com"]);
  const userEmails = new Set([
    "admin@acme.com",
    "member@acme.com",
    "outsider@example.com",
  ]);

  it("rejects invalid format", () => {
    expect(
      validateTenantContactEmail("not-an-email", tenantEmails, userEmails),
    ).toBe(EMAIL_INVALID_FORMAT_MSG);
  });

  it("rejects emails that belong to another account", () => {
    expect(
      validateTenantContactEmail(
        "outsider@example.com",
        tenantEmails,
        userEmails,
      ),
    ).toBe(EMAIL_USER_ALREADY_EXISTS_MSG);
  });

  it("allows an existing Institution Admin email for this institution", () => {
    expect(
      validateTenantContactEmail(
        "Admin@Acme.com",
        tenantEmails,
        userEmails,
        {
          excludeTenantEmail: "old@acme.com",
          excludeUserEmail: "old@acme.com",
          allowedUserEmails: new Set(["admin@acme.com"]),
        },
      ),
    ).toBeUndefined();
  });

  it("rejects a same-institution non-admin user email (BE 409 DUPLICATE_EMAIL)", () => {
    expect(
      validateTenantContactEmail(
        "member@acme.com",
        tenantEmails,
        userEmails,
        {
          allowedUserEmails: collectInstitutionAdminEmails([
            user("admin@acme.com", ["TENANT ADMIN"]),
            user("member@acme.com", ["USER"]),
          ]),
        },
      ),
    ).toBe(EMAIL_USER_ALREADY_EXISTS_MSG);
  });

  it("still rejects another institution contact email", () => {
    expect(
      validateTenantContactEmail(
        "other-tenant@example.com",
        tenantEmails,
        userEmails,
        { allowedUserEmails: new Set(["admin@acme.com"]) },
      ),
    ).toBe(EMAIL_ALREADY_EXISTS_MSG);
  });
});

describe("emailSetHas", () => {
  it("matches normalized emails in a Set or array", () => {
    expect(emailSetHas(new Set(["a@x.com"]), "A@X.com")).toBe(true);
    expect(emailSetHas(["a@x.com"], "A@X.com")).toBe(true);
    expect(emailSetHas(new Set(["a@x.com"]), "b@x.com")).toBe(false);
    expect(normalizeEmail(" A@X.com ")).toBe("a@x.com");
  });
});
