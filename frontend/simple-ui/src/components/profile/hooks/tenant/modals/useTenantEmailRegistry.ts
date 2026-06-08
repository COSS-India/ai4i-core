import { useCallback, useMemo, useState } from "react";
import authService from "../../../../../services/authService";
import * as tenantService from "../../../../../services/tenantService";
import {
  collectTenantContactEmails,
  collectUserEmails,
} from "../../../../../utils/tenantEmailValidation";
import type { TenantUserView, TenantView } from "../../../../../types/tenant";
import { resolveTenantManagementRoles, USER_EMAIL_PAGE_SIZE } from "../shared";
import type { TenantEmailRegistryState, UseTenantEmailRegistryOptions } from "./types";

export function useTenantEmailRegistry({
  user,
  tenants,
  tenantUsers,
}: UseTenantEmailRegistryOptions): TenantEmailRegistryState {
  const { isAdmin } = resolveTenantManagementRoles(user);

  const [knownTenantEmails, setKnownTenantEmails] = useState<Set<string>>(() => new Set());
  const [knownUserEmails, setKnownUserEmails] = useState<Set<string>>(() => new Set());
  const [isLoadingKnownEmails, setIsLoadingKnownEmails] = useState(false);

  const syncKnownEmailsFromLists = useCallback(
    (tenantRows: TenantView[], userRows: TenantUserView[]) => {
      setKnownTenantEmails(collectTenantContactEmails(tenantRows));
      setKnownUserEmails(collectUserEmails(userRows));
    },
    [],
  );

  const refreshKnownAccountEmails = useCallback(async () => {
    setIsLoadingKnownEmails(true);
    try {
      let tenantRows: TenantView[] = tenants;
      if (isAdmin) {
        tenantRows = (await tenantService.listTenants()).tenants ?? [];
      } else {
        const tenantId = user?.tenant_id?.trim();
        if (tenantId) {
          const own = await tenantService.getViewTenant(tenantId);
          tenantRows = own ? [own] : [];
        }
      }
      const tenantEmailSet = collectTenantContactEmails(tenantRows);
      const userEmailSet = new Set<string>(collectUserEmails(tenantUsers));

      let offset = 0;
      for (;;) {
        const batch = await authService.listUsersPage(offset, USER_EMAIL_PAGE_SIZE);
        for (const u of batch) {
          const e = (u.email ?? "").trim().toLowerCase();
          if (e) userEmailSet.add(e);
        }
        if (batch.length < USER_EMAIL_PAGE_SIZE) break;
        offset += USER_EMAIL_PAGE_SIZE;
      }

      setKnownTenantEmails(tenantEmailSet);
      setKnownUserEmails(userEmailSet);
    } catch (err) {
      console.error("Failed to load emails for uniqueness check:", err);
      syncKnownEmailsFromLists(tenants, tenantUsers);
    } finally {
      setIsLoadingKnownEmails(false);
    }
  }, [isAdmin, user?.tenant_id, tenants, tenantUsers, syncKnownEmailsFromLists]);

  const knownEmailRecheckKey = useMemo(
    () => (isLoadingKnownEmails ? "loading" : `${knownTenantEmails.size}:${knownUserEmails.size}`),
    [isLoadingKnownEmails, knownTenantEmails.size, knownUserEmails.size],
  );

  return {
    knownTenantEmails,
    knownUserEmails,
    isLoadingKnownEmails,
    knownEmailRecheckKey,
    syncKnownEmailsFromLists,
    refreshKnownAccountEmails,
  };
}
