import { useMemo, useState } from "react";
import authService from "../../../../services/authService";
import * as tenantService from "../../../../services/tenantService";
import { extractErrorInfo } from "../../../../utils/errorHandler";
import { collectTenantContactEmails } from "../../../../utils/tenantEmailValidation";
import { normalizeTenantStatus } from "../../../../config/constants";
import type { TenantStatus, TenantView } from "../../../../types/tenant";
import type { useToastWithDeduplication } from "../../../../hooks/useToastWithDeduplication";
import {
  resolveTenantManagementRoles,
  tenantMatchesSearch,
  type TenantManagementUser,
} from "./shared";

export interface UseTenantListOptions {
  user: TenantManagementUser | null;
  toast: ReturnType<typeof useToastWithDeduplication>;
  onOpenTenantStatus: (t: TenantView, newStatus: TenantStatus) => void;
  onTenantsLoaded?: (tenants: TenantView[]) => void;
}

export function useTenantList({
  user,
  toast,
  onOpenTenantStatus,
  onTenantsLoaded,
}: UseTenantListOptions) {
  const { isTenantScopedUser } = resolveTenantManagementRoles(user);

  const [tenants, setTenants] = useState<TenantView[]>([]);
  const [isLoadingTenants, setIsLoadingTenants] = useState(false);
  const [tenantFilterStatus, setTenantFilterStatus] = useState<string>("all");
  const [tenantSearch, setTenantSearch] = useState("");
  const [tenantDetailView, setTenantDetailView] = useState<TenantView | null>(null);
  const [tenantDetailSubTab, setTenantDetailSubTab] = useState<"overview" | "users">("overview");
  const [resendVerificationTenantId, setResendVerificationTenantId] = useState<string | null>(null);

  const filteredTenants = useMemo(
    () =>
      tenants.filter((t) => {
        if (
          tenantFilterStatus !== "all" &&
          normalizeTenantStatus(t.status) !== normalizeTenantStatus(tenantFilterStatus)
        ) {
          return false;
        }
        return tenantMatchesSearch(t, tenantSearch);
      }),
    [tenants, tenantFilterStatus, tenantSearch],
  );

  const handleFetchTenants = async () => {
    setIsLoadingTenants(true);
    try {
      if (isTenantScopedUser) {
        const tenantId = user?.tenant_id?.trim();
        if (!tenantId) {
          setTenants([]);
          onTenantsLoaded?.([]);
          return;
        }
        const tenant = await tenantService.getViewTenant(tenantId);
        const rows = tenant ? [tenant] : [];
        setTenants(rows);
        onTenantsLoaded?.(rows);
        return;
      }
      const res = await tenantService.listTenants();
      const rows = res.tenants ?? [];
      setTenants(rows);
      onTenantsLoaded?.(rows);
    } catch (err) {
      console.error("Failed to fetch tenants:", err);
      const { title, message } = extractErrorInfo(err);
      toast({ title, description: message, status: "error", isClosable: true, duration: 8000 });
      setTenants([]);
      onTenantsLoaded?.([]);
    } finally {
      setIsLoadingTenants(false);
    }
  };

  const resetTenantFilters = () => {
    setTenantFilterStatus("all");
    setTenantSearch("");
  };

  const openTenantDetail = (t: TenantView) => {
    setTenantDetailView(t);
    setTenantDetailSubTab("overview");
  };

  const closeTenantDetailView = () => {
    setTenantDetailView(null);
    setTenantDetailSubTab("overview");
  };

  const handleOpenTenantStatus = (t: TenantView, newStatus: TenantStatus) => {
    onOpenTenantStatus(t, newStatus);
  };

  const handleResendTenantVerificationEmail = async (t: TenantView) => {
    const email = t.email?.trim();
    if (!email) {
      toast({
        title: "Email required",
        description: "This tenant has no contact email to resend verification.",
        status: "warning",
        isClosable: true,
        duration: 5000,
      });
      return;
    }
    setResendVerificationTenantId(t.tenant_id);
    try {
      const res = await authService.resendSetupLink({ email }, { withAuth: true });
      toast({
        title: "Verification email sent",
        description:
          res?.message ??
          `A new activation link was sent to ${email} if the account is not yet activated.`,
        status: "success",
        isClosable: true,
        duration: 8000,
      });
    } catch (err) {
      console.error("Failed to resend tenant verification email:", err);
      const { title, message } = extractErrorInfo(err);
      toast({ title, description: message, status: "error", isClosable: true, duration: 6000 });
    } finally {
      setResendVerificationTenantId(null);
    }
  };

  return {
    tenants,
    setTenants,
    isLoadingTenants,
    filteredTenants,
    tenantFilterStatus,
    setTenantFilterStatus,
    tenantSearch,
    setTenantSearch,
    tenantDetailView,
    setTenantDetailView,
    tenantDetailSubTab,
    setTenantDetailSubTab,
    openTenantDetail,
    closeTenantDetailView,
    handleFetchTenants,
    resetTenantFilters,
    resendVerificationTenantId,
    handleOpenTenantStatus,
    handleResendTenantVerificationEmail,
    collectTenantEmails: (rows: TenantView[]) => collectTenantContactEmails(rows),
  };
}

export type UseTenantListReturn = ReturnType<typeof useTenantList>;
