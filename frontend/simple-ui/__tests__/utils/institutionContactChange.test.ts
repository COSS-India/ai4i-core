import { TENANT } from "../../src/config/constants";
import type { TenantUserView } from "../../src/types/tenant";
import {
  contactChangeBlockedMessage,
  listOtherActiveInstitutionAdmins,
  maskEmailForCompare,
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

describe("maskEmailForCompare", () => {
  it("matches auth-service mask_email shape", () => {
    expect(maskEmailForCompare("john.doe@example.com")).toBe("j***@e***.com");
    expect(maskEmailForCompare("alice@acme.com")).toBe("a***@a***.com");
  });
});

describe("listOtherActiveInstitutionAdmins (AI4IDS-3401 / AI4IDS-3617)", () => {
  it("offers other active, verified Institution Admins only", () => {
    const options = listOtherActiveInstitutionAdmins(
      [
        admin({
          user_id: "current",
          email: "a***@a***.com",
          full_name: "Current Contact",
        }),
        admin({
          user_id: "other",
          email: "p***@a***.com",
          full_name: "Priya Sharma",
        }),
        admin({
          user_id: "user",
          email: "u***@a***.com",
          roles: ["USER"],
          full_name: "A User",
        }),
        admin({
          user_id: "inactive",
          email: "i***@a***.com",
          is_active: false,
          full_name: "Inactive Admin",
        }),
        admin({
          user_id: "pending",
          email: "n***@a***.com",
          is_activated: false,
          full_name: "Not Verified",
        }),
      ],
      { contactEmail: "alice@acme.com" },
    );

    expect(options).toEqual([
      { userId: "other", label: "Priya Sharma · p***@a***.com" },
    ]);
  });

  it("returns no options when the sole admin is the current contact (AI4IDS-3617)", () => {
    expect(
      listOtherActiveInstitutionAdmins(
        [
          admin({
            user_id: "current",
            email: "a***@a***.com",
            full_name: "Current Contact",
          }),
        ],
        { contactEmail: "alice@acme.com" },
      ),
    ).toEqual([]);
  });

  it("still offers the sole remaining admin when the contact is already deactivated (AI4IDS-3401)", () => {
    // Contact Dana deactivated (not eligible); Eve is the only remaining
    // set-up admin and must remain pickable — never empty solely for count≤1.
    const options = listOtherActiveInstitutionAdmins(
      [
        admin({
          user_id: "dana",
          email: "d***@a***.com",
          full_name: "Dana",
          is_active: false,
        }),
        admin({
          user_id: "eve",
          email: "e***@a***.com",
          full_name: "Eve",
        }),
      ],
      { contactEmail: "dana@acme.com" },
    );

    expect(options).toEqual([{ userId: "eve", label: "Eve · e***@a***.com" }]);
  });

  it("lists all admins when contactEmail is absent", () => {
    const options = listOtherActiveInstitutionAdmins([
      admin({
        user_id: "current",
        email: "a***@a***.com",
        full_name: "Current Contact",
      }),
      admin({
        user_id: "other",
        email: "p***@a***.com",
        full_name: "Priya Sharma",
      }),
    ]);

    expect(options).toEqual([
      { userId: "current", label: "Current Contact · a***@a***.com" },
      { userId: "other", label: "Priya Sharma · p***@a***.com" },
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
