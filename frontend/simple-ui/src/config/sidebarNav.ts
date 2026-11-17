// Left navigation menu: items, per-role layouts, and visibility rules.

import { IconType } from "react-icons";
import {
  IoAppsOutline,
  IoCompassOutline,
  IoDocumentTextOutline,
  IoKeyOutline,
  IoNotificationsOutline,
  IoPeopleOutline,
  IoPricetagOutline,
  IoPulseOutline,
  IoServerOutline,
  IoShieldOutline,
  IoStatsChartOutline,
} from "react-icons/io5";
import {
  canAccessInstitutionManagement,
  canAccessNotificationsAlerts,
  canAccessServicesManagement,
  canAccessUsageDashboard,
  isAdopterInstitutionManager,
  isPlatformAdminUser,
  isTenantAdminUser,
  isUsageDashboardOnlyUser,
  userHasRole,
  userMayManageApiKeys,
} from "../utils/rbac";
import { INSTITUTION, INSTITUTIONS, TABS } from "./constants";

interface NavItemDef {
  /** Label used by the default layout. */
  label: string;
  /** Simplified label used by the admin layouts. */
  shortLabel: string;
  path: string;
  icon: IconType;
  requiresAuth: boolean;
}

const NAV_ITEMS = {
  [TABS.home]: {
    label: "Explore",
    shortLabel: "Playground",
    path: "/",
    icon: IoCompassOutline,
    requiresAuth: false,
  },
  [TABS.usageDashboard]: {
    label: "Usage Dashboard",
    shortLabel: "Usage",
    path: `/${TABS.usageDashboard}`,
    icon: IoStatsChartOutline,
    requiresAuth: true,
  },
  [TABS.logs]: {
    label: "Logs Dashboard",
    shortLabel: "Logs",
    path: `/${TABS.logs}`,
    icon: IoDocumentTextOutline,
    requiresAuth: true,
  },
  [TABS.traces]: {
    label: "Traces Dashboard",
    shortLabel: "Traces",
    path: `/${TABS.traces}`,
    icon: IoPulseOutline,
    requiresAuth: true,
  },
  [TABS.modelManagement]: {
    label: "Model Management",
    shortLabel: "Models",
    path: `/${TABS.modelManagement}`,
    icon: IoServerOutline,
    requiresAuth: true,
  },
  [TABS.servicesManagement]: {
    label: "Services Management",
    shortLabel: "Services",
    path: `/${TABS.servicesManagement}`,
    icon: IoAppsOutline,
    requiresAuth: true,
  },
  [TABS.tenantManagement]: {
    label: `${INSTITUTION} Management`,
    shortLabel: INSTITUTION,
    path: `/${TABS.tenantManagement}`,
    icon: IoPeopleOutline,
    requiresAuth: true,
  },
  [TABS.apiKeyManagement]: {
    label: "API Key Management",
    shortLabel: "API Keys",
    path: `/${TABS.apiKeyManagement}`,
    icon: IoKeyOutline,
    requiresAuth: true,
  },
  [TABS.notificationsAlerts]: {
    label: "Alerts & Notifications",
    shortLabel: "Alerts & Notifications",
    path: `/${TABS.notificationsAlerts}`,
    icon: IoNotificationsOutline,
    requiresAuth: true,
  },
  [TABS.tierManagement]: {
    label: "Tier Management",
    shortLabel: "Tiers",
    path: `/${TABS.tierManagement}`,
    icon: IoPricetagOutline,
    requiresAuth: true,
  },
  [TABS.policyManagement]: {
    label: "Policy Management",
    shortLabel: "Policies",
    path: `/${TABS.policyManagement}`,
    icon: IoShieldOutline,
    requiresAuth: true,
  },
} satisfies Record<string, NavItemDef>;

export type NavItemId = keyof typeof NAV_ITEMS;

interface NavEntry {
  id: NavItemId;
  /** Overrides the layout's label for this item. */
  label?: string;
}

interface NavSectionDef {
  id: string;
  /** No label = standalone item(s) shown without a group header. */
  label?: string;
  items: NavEntry[];
}

interface NavLayout {
  useShortLabels: boolean;
  sections: NavSectionDef[];
}

export interface NavItem extends NavItemDef {
  id: NavItemId;
}

export interface NavSection {
  id: string;
  label?: string;
  items: NavItem[];
}

/** Roles without a dedicated layout (User, Guest, Usage Viewer, signed out). */
const DEFAULT_NAV: NavLayout = {
  useShortLabels: false,
  sections: [
    { id: "try", label: "Try", items: [{ id: TABS.home }] },
    {
      id: "monitor",
      label: "Monitor",
      // Same label as the admin menus (only Usage Viewer sees this group).
      items: [
        { id: TABS.usageDashboard, label: NAV_ITEMS[TABS.usageDashboard].shortLabel },
        { id: TABS.logs },
        { id: TABS.traces },
      ],
    },
    {
      id: "manage",
      label: "Manage",
      items: [
        { id: TABS.modelManagement },
        { id: TABS.servicesManagement },
        { id: TABS.tenantManagement },
        { id: TABS.apiKeyManagement },
        { id: TABS.notificationsAlerts },
      ],
    },
    {
      id: "govern",
      label: "Govern",
      items: [{ id: TABS.tierManagement }, { id: TABS.policyManagement }],
    },
  ],
};

/** Adopter Admin (platform ADMIN / MODERATOR), grouped by priority of activity. */
const ADOPTER_ADMIN_NAV: NavLayout = {
  useShortLabels: true,
  sections: [
    { id: "monitor", label: "Monitor", items: [{ id: TABS.usageDashboard }, { id: TABS.logs }] },
    {
      id: "govern",
      label: "Govern",
      items: [{ id: TABS.policyManagement }, { id: TABS.notificationsAlerts }],
    },
    {
      id: "publish",
      label: "Publish/Provision",
      items: [
        { id: TABS.modelManagement },
        { id: TABS.servicesManagement },
        { id: TABS.tierManagement },
      ],
    },
    {
      id: "manage",
      label: "Manage",
      items: [{ id: TABS.tenantManagement, label: INSTITUTIONS }, { id: TABS.apiKeyManagement }],
    },
    { id: "playground", items: [{ id: TABS.home }] },
  ],
};

/** Institution Admin (TENANT ADMIN), grouped by priority of activity. */
const INSTITUTION_ADMIN_NAV: NavLayout = {
  useShortLabels: true,
  sections: [
    { id: "monitor", label: "Monitor", items: [{ id: TABS.usageDashboard }, { id: TABS.logs }] },
    {
      id: "govern",
      label: "Govern",
      items: [{ id: TABS.policyManagement }, { id: TABS.notificationsAlerts }],
    },
    {
      id: "manage",
      label: "Manage",
      items: [{ id: TABS.tenantManagement }, { id: TABS.apiKeyManagement }],
    },
    {
      id: "explore",
      label: "Explore",
      items: [{ id: TABS.modelManagement }, { id: TABS.home }],
    },
  ],
};

function getNavLayout(roles?: string[]): NavLayout {
  // Adopter side = platform ADMIN or MODERATOR. Items each role may not open
  // are still dropped by isNavItemVisible.
  if (isAdopterInstitutionManager(roles)) return ADOPTER_ADMIN_NAV;
  if (isTenantAdminUser(roles)) return INSTITUTION_ADMIN_NAV;
  return DEFAULT_NAV;
}

export interface NavVisibilityContext {
  isAuthenticated: boolean;
  /** Institution id from the access token, if any. */
  tenantId: string | null;
  roles?: string[];
}

export function isNavItemVisible(itemId: NavItemId, ctx: NavVisibilityContext): boolean {
  if (!ctx.isAuthenticated) {
    return itemId === TABS.home;
  }

  const { roles } = ctx;
  if (isUsageDashboardOnlyUser(roles)) {
    return itemId === TABS.usageDashboard;
  }

  const isAdmin = isPlatformAdminUser(roles);
  const isGuestOrUser = userHasRole(roles, "GUEST") || userHasRole(roles, "USER");

  switch (itemId) {
    case TABS.home:
      return true;
    case TABS.traces:
      return false;
    case TABS.policyManagement:
      return isAdmin || isTenantAdminUser(roles);
    case TABS.modelManagement:
      return !isGuestOrUser;
    case TABS.servicesManagement:
      return !isGuestOrUser && canAccessServicesManagement(roles);
    case TABS.tenantManagement:
      return canAccessInstitutionManagement(roles);
    case TABS.apiKeyManagement:
      return userMayManageApiKeys(roles);
    case TABS.logs:
      return !isGuestOrUser && Boolean(ctx.tenantId || isAdmin);
    case TABS.usageDashboard:
      return canAccessUsageDashboard(roles);
    case TABS.notificationsAlerts:
      return canAccessNotificationsAlerts(roles);
    case TABS.tierManagement:
      return isAdmin;
    default:
      return true;
  }
}

/** Ordered, role-filtered menu sections. Empty sections are dropped. */
export function getNavSections(ctx: NavVisibilityContext): NavSection[] {
  const layout = getNavLayout(ctx.isAuthenticated ? ctx.roles : undefined);
  return layout.sections
    .map((section) => ({
      id: section.id,
      label: section.label,
      items: section.items
        .filter((entry) => isNavItemVisible(entry.id, ctx))
        .map((entry): NavItem => {
          const def: NavItemDef = NAV_ITEMS[entry.id];
          return {
            ...def,
            id: entry.id,
            label: entry.label ?? (layout.useShortLabels ? def.shortLabel : def.label),
          };
        }),
    }))
    .filter((section) => section.items.length > 0);
}
