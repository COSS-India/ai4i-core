/// <reference types="jest" />

import { TENANT } from "../../src/config/constants";
import type { TenantView } from "../../src/types/tenant";
import {
  EMAIL_ALREADY_EXISTS_MSG,
  EMAIL_INVALID_FORMAT_MSG,
  EMAIL_REQUIRED_MSG,
  EMAIL_USER_ALREADY_EXISTS_MSG,
} from "../../src/utils/tenantEmailValidation";
import {
  CONTACT_NAME_REQUIRED_MSG,
  FULL_NAME_REQUIRED_MSG,
  NAME_INVALID_CHARS_MSG,
  NAME_NO_LETTER_MSG,
  NAME_TOO_LONG_MSG,
  NAME_TOO_SHORT_MSG,
  ORG_DUPLICATE_MSG,
  ORG_INVALID_CHARS_MSG,
  ORG_NO_ALNUM_MSG,
  ORG_REQUIRED_MSG,
  ORG_TOO_LONG_MSG,
  ORG_TOO_SHORT_MSG,
  PHONE_E164_MSG,
  PHONE_MAX_LENGTH_MSG,
} from "../../src/utils/tenantFormValidation";
import {
  collectAddUserErrors,
  collectCreateTenantErrors,
  collectEditTenantErrors,
  collectEditUserErrors,
} from "../../src/utils/tenantManagementValidation";

function tenant(overrides: Partial<TenantView> = {}): TenantView {
  return {
    tenant_id: "tenant-1",
    contact_name: "Ada Lovelace",
    organisation: "Acme",
    email: "ada@acme.com",
    status: TENANT.STATUS.ACTIVE,
    created_at: "2026-01-01T00:00:00.000Z",
    ...overrides,
  };
}

const validCreate = {
  organisation: "Acme Labs",
  contact_name: "Ada Lovelace",
  email: "ada@acme.com",
  phone_number: "",
  tenants: [] as TenantView[],
  knownTenantEmails: new Set<string>(),
  knownUserEmails: new Set<string>(),
};

describe("collectCreateTenantErrors", () => {
  it("returns no errors for a valid institution with an empty phone", () => {
    expect(collectCreateTenantErrors(validCreate)).toEqual({});
  });

  it("accepts a formatted E.164 phone", () => {
    expect(
      collectCreateTenantErrors({
        ...validCreate,
        phone_number: "+91 98765 43210",
      }),
    ).toEqual({});
  });

  it("reports every required field, and treats an empty phone as optional", () => {
    expect(
      collectCreateTenantErrors({
        ...validCreate,
        organisation: "   ",
        contact_name: "",
        email: "",
      }),
    ).toEqual({
      organisation: ORG_REQUIRED_MSG,
      contact_name: CONTACT_NAME_REQUIRED_MSG,
      email: EMAIL_REQUIRED_MSG,
    });
  });

  it("rejects an organisation that is too short before it checks uniqueness", () => {
    expect(
      collectCreateTenantErrors({
        ...validCreate,
        organisation: "A",
        tenants: [tenant({ organisation: "A" })],
      }).organisation,
    ).toBe(ORG_TOO_SHORT_MSG);
  });

  it("rejects an organisation on the length, character, and punctuation boundaries", () => {
    expect(
      collectCreateTenantErrors({
        ...validCreate,
        organisation: "A".repeat(101),
      }).organisation,
    ).toBe(ORG_TOO_LONG_MSG);
    expect(
      collectCreateTenantErrors({
        ...validCreate,
        organisation: "Acme@Labs",
      }).organisation,
    ).toBe(ORG_INVALID_CHARS_MSG);
    expect(
      collectCreateTenantErrors({
        ...validCreate,
        organisation: "---",
      }).organisation,
    ).toBe(ORG_NO_ALNUM_MSG);
    expect(
      collectCreateTenantErrors({
        ...validCreate,
        organisation: "A".repeat(100),
      }),
    ).toEqual({});
  });

  it("rejects a duplicate organisation name ignoring case and surrounding space", () => {
    expect(
      collectCreateTenantErrors({
        ...validCreate,
        organisation: "  acme  ",
        tenants: [tenant({ organisation: "ACME" })],
      }).organisation,
    ).toBe(ORG_DUPLICATE_MSG);
  });

  it("rejects a contact name that is too short, too long, or has no letter", () => {
    expect(
      collectCreateTenantErrors({ ...validCreate, contact_name: "A" }).contact_name,
    ).toBe(NAME_TOO_SHORT_MSG);
    expect(
      collectCreateTenantErrors({
        ...validCreate,
        contact_name: "A".repeat(81),
      }).contact_name,
    ).toBe(NAME_TOO_LONG_MSG);
    expect(
      collectCreateTenantErrors({ ...validCreate, contact_name: "12" }).contact_name,
    ).toBe(NAME_INVALID_CHARS_MSG);
  });

  it("prefers a user-account collision over a tenant-contact collision", () => {
    const taken = new Set(["ada@acme.com"]);
    expect(
      collectCreateTenantErrors({
        ...validCreate,
        email: " Ada@Acme.com ",
        knownTenantEmails: taken,
        knownUserEmails: taken,
      }).email,
    ).toBe(EMAIL_USER_ALREADY_EXISTS_MSG);
  });

  it("reports a tenant-contact collision when no user account has that email", () => {
    expect(
      collectCreateTenantErrors({
        ...validCreate,
        knownTenantEmails: new Set(["ada@acme.com"]),
      }).email,
    ).toBe(EMAIL_ALREADY_EXISTS_MSG);
  });

  it("rejects a malformed email before any collision check", () => {
    expect(
      collectCreateTenantErrors({
        ...validCreate,
        email: "not-an-email",
        knownUserEmails: new Set(["not-an-email"]),
      }).email,
    ).toBe(EMAIL_INVALID_FORMAT_MSG);
  });

  it("rejects a phone that is too long or not E.164, and skips a masked value", () => {
    expect(
      collectCreateTenantErrors({
        ...validCreate,
        phone_number: "+1234567890123456",
      }).phone_number,
    ).toBe(PHONE_MAX_LENGTH_MSG);
    expect(
      collectCreateTenantErrors({
        ...validCreate,
        phone_number: "9876543210",
      }).phone_number,
    ).toBe(PHONE_E164_MSG);
    expect(
      collectCreateTenantErrors({
        ...validCreate,
        phone_number: "+91******3210",
      }),
    ).toEqual({});
  });
});

describe("collectAddUserErrors", () => {
  const validUser = {
    lockedUserFormTenantId: "tenant-1" as string | null,
    tenant_id: "",
    full_name: "Grace Hopper",
    email: "grace@acme.com",
    phone_number: "",
    knownTenantEmails: new Set<string>(),
    knownUserEmails: new Set<string>(),
  };

  it("returns no errors when the institution is locked and the person is valid", () => {
    expect(collectAddUserErrors(validUser)).toEqual({});
  });

  it("requires an institution when neither the lock nor the field provides one", () => {
    expect(
      collectAddUserErrors({
        ...validUser,
        lockedUserFormTenantId: null,
        tenant_id: "   ",
      }).tenant_id,
    ).toBe("Institution is required.");
  });

  it("uses the locked institution and ignores a blank field", () => {
    expect(
      collectAddUserErrors({
        ...validUser,
        lockedUserFormTenantId: "tenant-9",
        tenant_id: "",
      }),
    ).toEqual({});
  });

  it("requires a full name, which is a different message from the contact name", () => {
    expect(collectAddUserErrors({ ...validUser, full_name: "" }).full_name).toBe(
      FULL_NAME_REQUIRED_MSG,
    );
  });

  it("uses the account-exists message for both user and tenant email collisions", () => {
    expect(
      collectAddUserErrors({
        ...validUser,
        knownUserEmails: new Set(["grace@acme.com"]),
      }).email,
    ).toBe(EMAIL_ALREADY_EXISTS_MSG);
    expect(
      collectAddUserErrors({
        ...validUser,
        knownTenantEmails: new Set(["grace@acme.com"]),
      }).email,
    ).toBe(EMAIL_ALREADY_EXISTS_MSG);
  });
});

describe("collectEditTenantErrors", () => {
  const editing = {
    organisation: "Acme",
    contact_name: "",
    email: "ada@acme.com",
    phone_number: "",
    tenant_id: "tenant-1",
    tenants: [tenant()],
    isEditTenantEmailEditable: false,
    knownTenantEmails: new Set(["ada@acme.com"]),
    knownUserEmails: new Set(["ada@acme.com"]),
    editTenantEmail: "ada@acme.com",
  };

  it("allows the current name and skips email when the address cannot be edited", () => {
    expect(
      collectEditTenantErrors({
        ...editing,
        email: "not-an-email",
      }),
    ).toEqual({});
  });

  it("still requires an organisation, and allows an empty contact name", () => {
    expect(
      collectEditTenantErrors({
        ...editing,
        organisation: undefined,
        contact_name: undefined,
      }),
    ).toEqual({ organisation: ORG_REQUIRED_MSG });
  });

  it("rejects another institution with the same name and keeps the current one", () => {
    expect(
      collectEditTenantErrors({
        ...editing,
        organisation: "Other Lab",
        tenants: [tenant(), tenant({ tenant_id: "tenant-2", organisation: "Other Lab" })],
      }).organisation,
    ).toBe(ORG_DUPLICATE_MSG);
    expect(
      collectEditTenantErrors({
        ...editing,
        organisation: "acme",
      }).organisation,
    ).toBeUndefined();
  });

  it("checks email only while editing, and ignores the address already on this institution", () => {
    expect(
      collectEditTenantErrors({
        ...editing,
        isEditTenantEmailEditable: true,
      }),
    ).toEqual({});
  });

  it("prefers a user collision when the edited email belongs to someone else", () => {
    expect(
      collectEditTenantErrors({
        ...editing,
        isEditTenantEmailEditable: true,
        email: "other@acme.com",
        knownUserEmails: new Set(["other@acme.com"]),
        knownTenantEmails: new Set(["other@acme.com"]),
      }).email,
    ).toBe(EMAIL_USER_ALREADY_EXISTS_MSG);
  });

  it("allows an existing Institution Admin email for this institution (AI4IDS-3401)", () => {
    expect(
      collectEditTenantErrors({
        ...editing,
        isEditTenantEmailEditable: true,
        email: "admin@acme.com",
        knownUserEmails: new Set(["ada@acme.com", "admin@acme.com"]),
        allowedUserEmails: new Set(["admin@acme.com"]),
      }),
    ).toEqual({});
  });

  it("rejects a short or letterless contact name, and an invalid phone", () => {
    expect(
      collectEditTenantErrors({ ...editing, contact_name: "A" }).contact_name,
    ).toBe(NAME_TOO_SHORT_MSG);
    expect(
      collectEditTenantErrors({ ...editing, contact_name: "--" }).contact_name,
    ).toBe(NAME_NO_LETTER_MSG);
    expect(
      collectEditTenantErrors({ ...editing, phone_number: "123" }).phone_number,
    ).toBe(PHONE_E164_MSG);
  });
});

describe("collectEditUserErrors", () => {
  it("returns no errors for a username of three characters and blank optional fields", () => {
    expect(
      collectEditUserErrors({
        username: "ada",
        full_name: "",
        phone_number: undefined,
      }),
    ).toEqual({});
  });

  it("requires a username of at least three characters after trimming", () => {
    expect(collectEditUserErrors({ username: "  ab  " }).username).toBe(
      "Username must be at least 3 characters.",
    );
    expect(collectEditUserErrors({ username: undefined }).username).toBe(
      "Username must be at least 3 characters.",
    );
    expect(
      collectEditUserErrors({ username: "  abc  " }).username,
    ).toBeUndefined();
  });

  it("validates an entered name and phone, and does not collect an email error", () => {
    expect(
      collectEditUserErrors({
        username: "ada",
        full_name: "A1",
        phone_number: "+91******3210",
      }),
    ).toEqual({ full_name: NAME_INVALID_CHARS_MSG });
  });
});
