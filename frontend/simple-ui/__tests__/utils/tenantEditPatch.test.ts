import { buildTenantEditPatch } from "../../src/utils/tenantEditPatch";

const baseline = {
  organisation: "Acme",
  contact_name: "Jane Doe",
  email: "jane@acme.com",
  phone_number: "+919876543210",
};

describe("buildTenantEditPatch (AI4IDS-3401)", () => {
  it("returns null when nothing changed", () => {
    expect(
      buildTenantEditPatch("1", baseline, { ...baseline }, {
        emailEditOpen: true,
      }),
    ).toBeNull();
  });

  it("sends only the edited field key/value", () => {
    expect(
      buildTenantEditPatch(
        "1",
        baseline,
        { ...baseline, phone_number: "+911234567890" },
      ),
    ).toEqual({
      tenant_id: "1",
      phone_number: "+911234567890",
    });

    expect(
      buildTenantEditPatch(
        "1",
        baseline,
        { ...baseline, organisation: "Acme Labs" },
      ),
    ).toEqual({
      tenant_id: "1",
      organisation: "Acme Labs",
    });
  });

  it("omits email unless Correct email is open and the address changed", () => {
    expect(
      buildTenantEditPatch(
        "1",
        baseline,
        { ...baseline, email: "other@acme.com", phone_number: "+91111" },
        { emailEditOpen: false },
      ),
    ).toEqual({
      tenant_id: "1",
      phone_number: "+91111",
    });

    expect(
      buildTenantEditPatch(
        "1",
        baseline,
        { ...baseline, email: "other@acme.com" },
        { emailEditOpen: true },
      ),
    ).toEqual({
      tenant_id: "1",
      email: "other@acme.com",
    });
  });

  it("sends contact_user_id for Change contact without echoing email", () => {
    expect(
      buildTenantEditPatch(
        "1",
        baseline,
        { ...baseline, contact_name: "New Name" },
        { selectedContactUserId: "admin-2", emailEditOpen: true },
      ),
    ).toEqual({
      tenant_id: "1",
      contact_name: "New Name",
      contact_user_id: "admin-2",
    });
  });
});
