import { TABS } from "../config/constants";
import { METERING } from "../config/meteringConstants";
import authService from "../services/authService";
import { canAccessUsageDashboard, getMeteringRoleViewConfig } from "./rbac";

export const APP_HOME_PATH = "/";
export const USAGE_DASHBOARD_PATH = `/${TABS.usageDashboard}`;

function resolveRoles(roles?: string[]): string[] | undefined {
  if (roles?.length) return roles;
  return authService.getStoredUser()?.roles;
}

export function getUsageDashboardPath(tab?: string): string {
  if (!tab) return USAGE_DASHBOARD_PATH;
  return `${USAGE_DASHBOARD_PATH}?tab=${encodeURIComponent(tab)}`;
}

export function getUsageDashboardOverviewPath(): string {
  return getUsageDashboardPath(METERING.SUB_TAB.OVERVIEW);
}

/** Role-aware post-login destination (Usage Dashboard when permitted, else services home). */
export function getDefaultLandingPath(roles?: string[]): string {
  // Previous default: always land on services home.
  // return APP_HOME_PATH;

  const effectiveRoles = resolveRoles(roles);
  if (!canAccessUsageDashboard(effectiveRoles)) {
    return APP_HOME_PATH;
  }

  const { defaultView } = getMeteringRoleViewConfig(effectiveRoles);
  const tab =
    defaultView === "tenant"
      ? METERING.DEFAULTS.TENANT_SUB_TAB
      : METERING.DEFAULTS.SUB_TAB;

  return getUsageDashboardPath(tab);
}
