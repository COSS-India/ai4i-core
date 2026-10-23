import {
  EMAIL_ALREADY_EXISTS_MSG,
  EMAIL_INVALID_FORMAT_MSG,
  EMAIL_USER_ALREADY_EXISTS_MSG,
  collectInstitutionAdminEmails,
  collectInstitutionUserEmails,
  emailSetHas,
  normalizeEmail,
  validateTenantContactEmail,
} from "../../src/utils/tenantEmailValidation";
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

describe("collectInstitutionUserEmails (AI4IDS-3401)", () => {
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
          allowedUserEmails: new Set(["admin@acme.com", "member@acme.com"]),
        },
      ),
    ).toBeUndefined();
  });

  it("allows a same-institution non-admin user email for uniqueness", () => {
    expect(
      validateTenantContactEmail(
        "member@acme.com",
        tenantEmails,
        userEmails,
        {
          allowedUserEmails: collectInstitutionUserEmails([
            user("admin@acme.com", ["TENANT ADMIN"]),
            user("member@acme.com", ["USER"]),
          ]),
        },
      ),
    ).toBeUndefined();
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
