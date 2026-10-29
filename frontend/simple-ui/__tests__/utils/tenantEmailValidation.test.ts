import {
  EMAIL_ALREADY_EXISTS_MSG,
  EMAIL_INVALID_FORMAT_MSG,
  EMAIL_USER_ALREADY_EXISTS_MSG,
  extractApiErrorCode,
  isTenantContactEmailEditable,
  mapTenantEmailConflictToFieldError,
  resolveTenantEmailUpdateFeedback,
  validateTenantContactEmail,
} from "../../src/utils/tenantEmailValidation";
import { INSTITUTION, TENANT } from "../../src/config/constants";
import { runEmailAvailabilityCheck } from "../../src/utils/tenantEmailAvailability";

describe("isTenantContactEmailEditable (AI4IDS-3401)", () => {
  it("allows typed email for PENDING only (ACTIVE uses Change contact)", () => {
    expect(isTenantContactEmailEditable(TENANT.STATUS.PENDING)).toBe(true);
    expect(isTenantContactEmailEditable(TENANT.STATUS.ACTIVE)).toBe(false);
    expect(isTenantContactEmailEditable(TENANT.STATUS.SUSPENDED)).toBe(false);
    expect(isTenantContactEmailEditable(TENANT.STATUS.DEACTIVATED)).toBe(false);
    expect(isTenantContactEmailEditable(undefined)).toBe(false);
  });

  it("locks the Default Organisation even when PENDING", () => {
    expect(
      isTenantContactEmailEditable(TENANT.STATUS.PENDING, {
        isDefaultOrganisation: true,
      }),
    ).toBe(false);
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

describe("mapTenantEmailConflictToFieldError (AI4IDS-3401)", () => {
  function conflict(code: string, message: string) {
    return {
      response: {
        status: 409,
        data: { detail: { code, message } },
      },
    };
  }

  it("maps DUPLICATE_EMAIL / DUPLICATE_TENANT_EMAIL to an inline message", () => {
    expect(
      mapTenantEmailConflictToFieldError(
        conflict("DUPLICATE_EMAIL", "This email is already in use."),
      ),
    ).toBe("This email is already in use.");
    expect(
      mapTenantEmailConflictToFieldError(
        conflict("DUPLICATE_TENANT_EMAIL", "A tenant with this email already exists."),
      ),
    ).toBe("A tenant with this email already exists.");
    expect(extractApiErrorCode(conflict("DUPLICATE_EMAIL", "x"))).toBe(
      "DUPLICATE_EMAIL",
    );
  });

  it("ignores other errors so the caller can toast them", () => {
    expect(
      mapTenantEmailConflictToFieldError(
        conflict("TENANT_EMAIL_EDIT_NOT_ALLOWED", "Locked"),
      ),
    ).toBeUndefined();
  });

  it("falls back to EMAIL_ALREADY_EXISTS_MSG when detail has no message", () => {
    expect(
      mapTenantEmailConflictToFieldError({
        message: "Request failed with status code 409",
        response: {
          status: 409,
          data: { detail: { code: "DUPLICATE_EMAIL" } },
        },
      }),
    ).toBe(EMAIL_ALREADY_EXISTS_MSG);
  });
});

describe("runEmailAvailabilityCheck skipUserCollision (AI4IDS-3401)", () => {
  it("returns unchecked — not available — when user checks are deferred to PATCH", async () => {
    const result = await runEmailAvailabilityCheck({
      email: "new@acme.com",
      mode: "tenant_contact",
      tenantEmails: new Set(),
      userEmails: new Set(["other@acme.com"]),
      skipUserCollision: true,
    });
    expect(result).toEqual({ status: "unchecked" });
  });
});

describe("validateTenantContactEmail", () => {
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

  it("still rejects another institution contact email", () => {
    expect(
      validateTenantContactEmail(
        "other-tenant@example.com",
        tenantEmails,
        userEmails,
      ),
    ).toBe(EMAIL_ALREADY_EXISTS_MSG);
  });
});
