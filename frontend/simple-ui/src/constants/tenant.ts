// Tenant lifecycle statuses and UI helpers

/** Tenant lifecycle and user statuses (auth-service). Canonical values are UPPERCASE. */
export const TENANT = {
  STATUS: {
    PENDING: "PENDING",
    ACTIVE: "ACTIVE",
    SUSPENDED: "SUSPENDED",
    DEACTIVATED: "DEACTIVATED",
  },
  USER_STATUS: {
    PENDING: "PENDING",
    ACTIVE: "ACTIVE",
    /** UI-only: user has not completed setup / password (is_active=false, not tenant-suspended). */
    PENDING_ACTIVATION: "PENDING_ACTIVATION",
    SUSPENDED: "SUSPENDED",
  },
} as const;

export type TenantStatusValue = (typeof TENANT.STATUS)[keyof typeof TENANT.STATUS];
export type TenantUserStatusValue = (typeof TENANT.USER_STATUS)[keyof typeof TENANT.USER_STATUS];

/** All tenant lifecycle statuses (static; used for filters and labels). */
export const TENANT_STATUS_LIST: readonly TenantStatusValue[] = [
  TENANT.STATUS.PENDING,
  TENANT.STATUS.ACTIVE,
  TENANT.STATUS.SUSPENDED,
  TENANT.STATUS.DEACTIVATED,
];

/** Statuses an admin may set via PATCH (excludes PENDING). */
export const TENANT_ADMIN_UPDATABLE_STATUSES: readonly TenantStatusValue[] = [
  TENANT.STATUS.ACTIVE,
  TENANT.STATUS.SUSPENDED,
  TENANT.STATUS.DEACTIVATED,
];

/** Allowed PATCH transitions — keep in sync with auth-service tenant_lifecycle.py. */
export const ALLOWED_TENANT_STATUS_TRANSITIONS: Readonly<
  Record<TenantStatusValue, readonly TenantStatusValue[]>
> = {
  [TENANT.STATUS.PENDING]: [TENANT.STATUS.DEACTIVATED],
  [TENANT.STATUS.ACTIVE]: [TENANT.STATUS.SUSPENDED, TENANT.STATUS.DEACTIVATED],
  [TENANT.STATUS.SUSPENDED]: [TENANT.STATUS.ACTIVE, TENANT.STATUS.DEACTIVATED],
  [TENANT.STATUS.DEACTIVATED]: [TENANT.STATUS.ACTIVE],
};

/** Tenant-user lifecycle statuses for filters and badges (not tenant PENDING/DEACTIVATED). */
export const TENANT_USER_STATUS_LIST: readonly TenantUserStatusValue[] = [
  TENANT.USER_STATUS.PENDING,
  TENANT.USER_STATUS.ACTIVE,
  TENANT.USER_STATUS.PENDING_ACTIVATION,
  TENANT.USER_STATUS.SUSPENDED,
];

/** Minimal fields needed to derive tenant-user display status. */
export type TenantUserStatusSource = {
  is_active: boolean;
  is_tenant_active?: boolean | null;
};

/** True when tenant lifecycle status blocks all users at the tenant level. */
export function isTenantLifecycleBlockingUsers(
  tenantStatus?: string | null
): boolean {
  return (
    isTenantStatus(tenantStatus, TENANT.STATUS.SUSPENDED) ||
    isTenantStatus(tenantStatus, TENANT.STATUS.DEACTIVATED)
  );
}

/**
 * Derive tenant-user display status for UI badges and action menus.
 * When ``tenantStatus`` is SUSPENDED/DEACTIVATED, all users show Suspended
 * (per multi-tenant cascade spec) even if per-user flags are stale.
 */
export function resolveTenantUserDisplayStatus(
  user: TenantUserStatusSource,
  tenantStatus?: string | null
): TenantUserStatusValue {
  if (isTenantLifecycleBlockingUsers(tenantStatus)) {
    return TENANT.USER_STATUS.SUSPENDED;
  }

  if (user.is_active && (user.is_tenant_active ?? true)) {
    return TENANT.USER_STATUS.ACTIVE;
  }
  if (!user.is_active && user.is_tenant_active === false) {
    return TENANT.USER_STATUS.SUSPENDED;
  }
  if (!user.is_active) {
    return TENANT.USER_STATUS.PENDING_ACTIVATION;
  }
  return TENANT.USER_STATUS.SUSPENDED;
}

/** Status to apply when toggling Suspend/Activate on a tenant user. */
export function getTenantUserStatusToggleTarget(
  user: TenantUserStatusSource
): TenantUserStatusValue {
  const display = resolveTenantUserDisplayStatus(user);
  return display === TENANT.USER_STATUS.ACTIVE
    ? TENANT.USER_STATUS.SUSPENDED
    : TENANT.USER_STATUS.ACTIVE;
}

/** Suspend/Activate action label for tenant users (Delete is a separate action). */
export function getTenantUserStatusActionLabel(user: TenantUserStatusSource): string {
  const display = resolveTenantUserDisplayStatus(user);
  if (display === TENANT.USER_STATUS.ACTIVE) return "Suspend";
  if (display === TENANT.USER_STATUS.SUSPENDED) return "Activate";
  // Not used in the new Pending actions menu, but keep a sensible default.
  return "Activate";
}

const TENANT_STATUS_LABELS: Record<TenantStatusValue, string> = {
  [TENANT.STATUS.PENDING]: "Pending Activation",
  [TENANT.STATUS.ACTIVE]: "Active",
  [TENANT.STATUS.SUSPENDED]: "Suspended",
  [TENANT.STATUS.DEACTIVATED]: "Deactivated",
};

const TENANT_USER_STATUS_LABELS: Record<TenantUserStatusValue, string> = {
  [TENANT.USER_STATUS.PENDING]: "Pending",
  [TENANT.USER_STATUS.ACTIVE]: "Active",
  [TENANT.USER_STATUS.PENDING_ACTIVATION]: "Pending Activation",
  [TENANT.USER_STATUS.SUSPENDED]: "Suspended",
};

export function normalizeTenantStatus(status: string): TenantStatusValue {
  return status.trim().toUpperCase() as TenantStatusValue;
}

/** Title-case label for tenant lifecycle status (UI only). */
export function formatTenantStatusLabel(status: string | null | undefined): string {
  if (!status?.trim()) return "—";
  const normalized = normalizeTenantStatus(status);
  return TENANT_STATUS_LABELS[normalized] ?? status;
}

/** Title-case label for tenant user status (UI only). */
export function formatTenantUserStatusLabel(status: string | null | undefined): string {
  if (!status?.trim()) return "—";
  const upper = status.trim().toUpperCase();
  if (upper in TENANT_USER_STATUS_LABELS) {
    return TENANT_USER_STATUS_LABELS[upper as TenantUserStatusValue];
  }
  return status;
}

export function isTenantStatus(
  actual: string | null | undefined,
  expected: TenantStatusValue
): boolean {
  return normalizeTenantStatus(actual ?? "") === expected;
}

export function isTenantUserStatus(
  actual: string | null | undefined,
  expected: TenantUserStatusValue
): boolean {
  return (actual ?? "").trim().toUpperCase() === expected;
}

/** Chakra colorScheme for tenant / tenant-user status badges. */
export function getTenantStatusColorScheme(status?: string | null): string {
  if (isTenantStatus(status, TENANT.STATUS.ACTIVE)) return "green";
  if (isTenantStatus(status, TENANT.STATUS.SUSPENDED)) return "orange";
  if (isTenantStatus(status, TENANT.STATUS.DEACTIVATED)) return "red";
  if (isTenantStatus(status, TENANT.STATUS.PENDING)) return "blue";
  if (isTenantUserStatus(status, TENANT.USER_STATUS.PENDING_ACTIVATION)) return "blue";
  if (isTenantUserStatus(status, TENANT.USER_STATUS.SUSPENDED)) return "orange";
  if (isTenantUserStatus(status, TENANT.USER_STATUS.PENDING)) return "gray";
  return "gray";
}

/** Target statuses offered as row actions for the given tenant status. */
export function getTenantStatusActionTargets(
  currentStatus: string | null | undefined
): TenantStatusValue[] {
  const current = normalizeTenantStatus(currentStatus ?? "");
  return [...(ALLOWED_TENANT_STATUS_TRANSITIONS[current] ?? [])];
}

/** Action button label when changing tenant status. */
export function getTenantStatusActionLabel(
  targetStatus: TenantStatusValue,
  currentStatus?: string | null
): string {
  const current = currentStatus ? normalizeTenantStatus(currentStatus) : null;
  if (
    targetStatus === TENANT.STATUS.ACTIVE &&
    current === TENANT.STATUS.DEACTIVATED
  ) {
    return "Reactivate";
  }
  switch (targetStatus) {
    case TENANT.STATUS.ACTIVE:
      return "Activate";
    case TENANT.STATUS.SUSPENDED:
      return "Suspend";
    case TENANT.STATUS.DEACTIVATED:
      return "Deactivate";
    default:
      return formatTenantStatusLabel(targetStatus);
  }
}

/** Profile timezone picker options. */
export const TIMEZONES = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "Europe/London",
  "Europe/Paris",
  "Europe/Berlin",
  "Asia/Kolkata",
  "Asia/Tokyo",
  "Asia/Shanghai",
  "Australia/Sydney",
] as const;
