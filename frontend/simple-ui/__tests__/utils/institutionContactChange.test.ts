import { TENANT } from "../../src/config/constants";
import type { TenantUserView } from "../../src/types/tenant";
import {
  contactChangeBlockedMessage,
  listOtherActiveInstitutionAdmins,
} from "../../src/utils/institutionContactChange";
import { FIELD_HINTS } from "../../src/config/fieldHints";

function admin(
  overrides: Partial<TenantUserView> & Pick<TenantUserView, "user_id" | "email">,
): TenantUserView {
  return {
    username: overrides.email.split("@")[0] ?? "user",
    is_active: true,
    is_activated: true,
    roles: ["TENANT ADMIN"],
    ...overrides,
  };
}

describe("listOtherActiveInstitutionAdmins (AI4IDS-3401)", () => {
  it("offers other active, verified Institution Admins only", () => {
    const options = listOtherActiveInstitutionAdmins(
      [
        admin({
          user_id: "current",
          email: "A***@acme.com",
          full_name: "Current Contact",
        }),
        admin({
          user_id: "other",
          email: "p***@acme.com",
          full_name: "Priya Sharma",
        }),
        admin({
          user_id: "user",
          email: "u***@acme.com",
          roles: ["USER"],
          full_name: "A User",
        }),
        admin({
          user_id: "inactive",
          email: "i***@acme.com",
          is_active: false,
          full_name: "Inactive Admin",
        }),
        admin({
          user_id: "pending",
          email: "n***@acme.com",
          is_activated: false,
          full_name: "Not Verified",
        }),
      ],
      { excludeUserId: "current" },
    );

    expect(options).toEqual([
      { userId: "other", label: "Priya Sharma · p***@acme.com" },
    ]);
  });

  it("returns no options for a sole admin when excludeUserId is absent (AI4IDS-3617)", () => {
    expect(
      listOtherActiveInstitutionAdmins([
        admin({
          user_id: "current",
          email: "a***@acme.com",
          full_name: "Current Contact",
        }),
      ]),
    ).toEqual([]);
  });

  it("lists all admins when excludeUserId is absent but alternatives exist", () => {
    const options = listOtherActiveInstitutionAdmins([
      admin({
        user_id: "current",
        email: "a***@acme.com",
        full_name: "Current Contact",
      }),
      admin({
        user_id: "other",
        email: "p***@acme.com",
        full_name: "Priya Sharma",
      }),
    ]);

    expect(options).toEqual([
      { userId: "current", label: "Current Contact · a***@acme.com" },
      { userId: "other", label: "Priya Sharma · p***@acme.com" },
    ]);
  });
});

describe("contactChangeBlockedMessage (AI4IDS-3401)", () => {
  it("blocks pending, suspended, deactivated, and the Default Organisation", () => {
    expect(contactChangeBlockedMessage(TENANT.STATUS.PENDING)).toBe(
      FIELD_HINTS.tenant.contactChangePending,
    );
    expect(contactChangeBlockedMessage(TENANT.STATUS.SUSPENDED)).toBe(
      FIELD_HINTS.tenant.contactChangeSuspended,
    );
    expect(contactChangeBlockedMessage(TENANT.STATUS.DEACTIVATED)).toBe(
      FIELD_HINTS.tenant.contactChangeDeactivated,
    );
    expect(
      contactChangeBlockedMessage(TENANT.STATUS.ACTIVE, {
        isDefaultOrganisation: true,
      }),
    ).toBe(FIELD_HINTS.tenant.contactChangeDefaultOrg);
  });

  it("allows Active institutions only", () => {
    expect(contactChangeBlockedMessage(TENANT.STATUS.ACTIVE)).toBeNull();
  });

  it("uses a neutral message for other non-editable statuses", () => {
    expect(contactChangeBlockedMessage("UNKNOWN")).toBe(
      FIELD_HINTS.tenant.contactChangeUnavailable,
    );
  });
});
