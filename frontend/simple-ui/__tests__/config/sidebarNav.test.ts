/// <reference types="jest" />

import {
  IoAppsOutline,
  IoCompassOutline,
  IoDocumentTextOutline,
  IoKeyOutline,
  IoNotificationsOutline,
  IoPeopleOutline,
  IoPricetagOutline,
  IoServerOutline,
  IoShieldOutline,
  IoStatsChartOutline,
} from "react-icons/io5";
import { getNavSections, type NavSection } from "../../src/config/sidebarNav";

/** "Group: Item, Item" lines; standalone sections have no "Group:" prefix. */
function outline(sections: NavSection[]): string[] {
  return sections.map((s) => {
    const items = s.items.map((i) => i.label).join(", ");
    return s.label ? `${s.label}: ${items}` : items;
  });
}

const signedIn = (roles: string[], tenantId: string | null = "tenant-1") =>
  getNavSections({ isAuthenticated: true, tenantId, roles });

describe("Institution Admin menu", () => {
  const sections = signedIn(["TENANT_ADMIN"]);

  it("shows the groups in priority order with Playground standalone at the bottom", () => {
    expect(outline(sections)).toEqual([
      "Monitor: Usage, Logs",
      "Govern: Policies, Alerts & Notifications",
      "Catalog: Models",
      "Manage: Institution, API Keys",
      "Playground",
    ]);
    expect(sections[sections.length - 1].label).toBeUndefined();
  });

  it("does not show Services Management", () => {
    const ids = sections.flatMap((s) => s.items.map((i) => i.id));
    expect(ids.includes("services-management")).toBe(false);
  });

  it("keeps each item's existing page and icon", () => {
    const items = sections.flatMap((s) => s.items);
    expect(items.map((i) => [i.label, i.path, i.icon])).toEqual([
      ["Usage", "/usage-dashboard", IoStatsChartOutline],
      ["Logs", "/logs", IoDocumentTextOutline],
      ["Policies", "/policy-management", IoShieldOutline],
      ["Alerts & Notifications", "/notifications-alerts", IoNotificationsOutline],
      ["Models", "/model-management", IoServerOutline],
      ["Institution", "/institution-management", IoPeopleOutline],
      ["API Keys", "/api-key-management", IoKeyOutline],
      ["Playground", "/", IoCompassOutline],
    ]);
  });
});

describe("Adopter Admin menu", () => {
  const sections = signedIn(["ADMIN"]);

  it("shows the groups in priority order with Playground standalone at the bottom", () => {
    expect(outline(sections)).toEqual([
      "Monitor: Usage, Logs",
      "Govern: Policies, Alerts & Notifications",
      "Catalog: Models, Services, Tiers",
      "Manage: Institutions, API Keys",
      "Playground",
    ]);
    expect(sections[sections.length - 1].label).toBeUndefined();
  });

  it("keeps each item's existing page and icon", () => {
    const items = sections.flatMap((s) => s.items);
    expect(items.map((i) => [i.label, i.path, i.icon])).toEqual([
      ["Usage", "/usage-dashboard", IoStatsChartOutline],
      ["Logs", "/logs", IoDocumentTextOutline],
      ["Policies", "/policy-management", IoShieldOutline],
      ["Alerts & Notifications", "/notifications-alerts", IoNotificationsOutline],
      ["Models", "/model-management", IoServerOutline],
      ["Services", "/services-management", IoAppsOutline],
      ["Tiers", "/tier-management", IoPricetagOutline],
      ["Institutions", "/institution-management", IoPeopleOutline],
      ["API Keys", "/api-key-management", IoKeyOutline],
      ["Playground", "/", IoCompassOutline],
    ]);
  });

  it("wins over Institution Admin when a user holds both roles", () => {
    expect(outline(signedIn(["ADMIN", "TENANT ADMIN"]))[2]).toBe(
      "Catalog: Models, Services, Tiers",
    );
  });

  it("uses the same layout for MODERATOR, keeping its existing access", () => {
    expect(outline(signedIn(["MODERATOR"]))).toEqual([
      "Monitor: Logs",
      "Catalog: Models, Services",
      "Playground",
    ]);
  });
});

describe("other roles keep the existing menu", () => {
  it("signed out: Explore only", () => {
    expect(outline(getNavSections({ isAuthenticated: false, tenantId: null }))).toEqual([
      "Try: Explore",
    ]);
  });

  it("USER: Explore only", () => {
    expect(outline(signedIn(["USER"]))).toEqual(["Try: Explore"]);
  });

  it("USAGE VIEWER: Usage only, labelled like the admin menus", () => {
    expect(outline(signedIn(["USAGE_VIEWER"]))).toEqual(["Monitor: Usage"]);
  });
});
