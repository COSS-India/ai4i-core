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
  const current = "a***@acme.com";

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
      current,
    );

    expect(options).toEqual([
      { userId: "other", label: "Priya Sharma · p***@acme.com" },
    ]);
  });
});

describe("contactChangeBlockedMessage (AI4IDS-3401)", () => {
  it("blocks suspended, deactivated, and the Default Organisation", () => {
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

  it("allows Pending and Active institutions", () => {
    expect(contactChangeBlockedMessage(TENANT.STATUS.PENDING)).toBeNull();
    expect(contactChangeBlockedMessage(TENANT.STATUS.ACTIVE)).toBeNull();
  });
});
