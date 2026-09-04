import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import { useDisclosure } from "@chakra-ui/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSessionExpiry } from "./useSessionExpiry";
import { useToastWithDeduplication } from "../utils/toast";
import { extractErrorInfo } from "../utils/errorHandler";
import {
  fetchTiers,
  createTier,
  updateTier,
  deleteTier,
  fetchTenantTiers,
  type Tier,
} from "../services/tierManagementService";
import { listTenants } from "../services/tenantService";
import { INSTITUTION } from "../config/constants";
import { fetchAllServicesMatchingFilters } from "../services/servicesManagementService";
import { useInferenceTypes } from "./useInferenceTypes";
import { generateUUID } from "../utils/uuid";
import type { TierFormData, TierFormQuota } from "../types/tierManagement";

const TIER_QUERY_KEY = "tiers";

function newQuota(): TierFormQuota {
  return {
    _key: generateUUID(),
    modelTaskType: "",
    unit: "",
    limit: "",
  };
}

function defaultFormData(): TierFormData {
  return { name: "", description: "", quotas: [newQuota()] };
}

/**
 * Validate the quota rows of a tier form. Returns a user-facing error message
 * for the first problem found, or null when every row is valid. Enforces that
 * each row has a model task type, a non-empty unit, and a limit strictly
 * greater than 0 (rejecting empty, non-numeric, 0, and negative limits).
 */
function validateQuotas(quotas: TierFormQuota[]): string | null {
  for (const q of quotas) {
    if (!q.modelTaskType) {
      return "Each quota must have a model task type.";
    }
    if (!q.unit.trim()) {
      return "Unit is required for each quota.";
    }
    const limitNum = Number(q.limit);
    if (q.limit.trim() === "" || !Number.isFinite(limitNum) || limitNum <= 0) {
      return "Limit must be greater than 0.";
    }
  }
  return null;
}

export function useTierManagement() {
  const toast = useToastWithDeduplication();
  const queryClient = useQueryClient();
  const { checkSessionExpiry } = useSessionExpiry();
  const {
    unitByTaskType,
    taskTypeNames,
    isLoading: isLoadingTaskTypes,
  } = useInferenceTypes();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterTaskType, setFilterTaskType] = useState("");
  const didInitTaskTypeFilter = useRef(false);
  const [taskTypeFilterReady, setTaskTypeFilterReady] = useState(false);
  useEffect(() => {
    if (didInitTaskTypeFilter.current || isLoadingTaskTypes) return;
    didInitTaskTypeFilter.current = true;
    // Single enabled type → lock filter to it (no All). Multiple → default All ("").
    if (taskTypeNames.length === 1) setFilterTaskType(taskTypeNames[0]);
    setTaskTypeFilterReady(true);
  }, [isLoadingTaskTypes, taskTypeNames]);

  const [tierToDelete, setTierToDelete] = useState<Tier | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const [viewTierId, setViewTierId] = useState<string | null>(null);
  const [formData, setFormData] = useState<TierFormData>(defaultFormData);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showQuotaErrors, setShowQuotaErrors] = useState(false);
  const [editingTier, setEditingTier] = useState<Tier | null>(null);

  const [scheduleTarget, setScheduleTarget] = useState<TierFormQuota | null>(
    null,
  );
  const [scheduleLimit, setScheduleLimit] = useState("");
  const [isScheduling, setIsScheduling] = useState(false);
  const [cancelingTaskType, setCancelingTaskType] = useState<string | null>(
    null,
  );
  const [removingTaskType, setRemovingTaskType] = useState<string | null>(null);

  const {
    isOpen: isDeleteOpen,
    onOpen: onDeleteOpen,
    onClose: onDeleteClose,
  } = useDisclosure();
  const {
    isOpen: isCreateOpen,
    onOpen: onCreateOpen,
    onClose: onCreateClose,
  } = useDisclosure();
  const {
    isOpen: isEditOpen,
    onOpen: onEditOpen,
    onClose: onEditClose,
  } = useDisclosure();
  const {
    isOpen: isViewOpen,
    onOpen: onViewOpen,
    onClose: onViewClose,
  } = useDisclosure();
  const {
    isOpen: isScheduleOpen,
    onOpen: onScheduleOpen,
    onClose: onScheduleClose,
  } = useDisclosure();

  // Frontend-enabled task types (ENABLED_TASK_TYPES). Used to scope "All" fetches.
  const enabledTaskTypesParam =
    taskTypeNames.length > 0 ? taskTypeNames.join(",") : undefined;

  const tiersQuery = useQuery({
    queryKey: [TIER_QUERY_KEY, filterTaskType || enabledTaskTypesParam || "all"],
    queryFn: () =>
      fetchTiers(filterTaskType || enabledTaskTypesParam || undefined),
    staleTime: 30 * 1000,
    retry: 1,
    enabled: taskTypeFilterReady,
  });

  const tiers = tiersQuery.data?.data ?? [];

  const viewTier = useMemo(
    () => tiers.find((t) => t.id === viewTierId) ?? null,
    [tiers, viewTierId],
  );

  // Tenant→tier assignments. Shares the ["tenant-tiers"] query key with the
  // Tenant Management tab so assigning a tier there keeps this view in sync.
  const tenantTiersQuery = useQuery({
    queryKey: ["tenant-tiers"],
    queryFn: () => fetchTenantTiers(),
    staleTime: 30 * 1000,
    enabled: !!viewTierId,
  });

  // Tenant directory, used to resolve tenant_id → organisation name for display.
  // limit is capped at 500 by the auth-service tenants endpoint (le=500).
  const tenantsDirectoryQuery = useQuery({
    queryKey: ["tenants-directory"],
    queryFn: () => listTenants({ limit: 500 }),
    staleTime: 5 * 60 * 1000,
    enabled: !!viewTierId,
  });

  const assignedTenantsForViewTier = useMemo(() => {
    if (!viewTier) return [];
    const assignments = tenantTiersQuery.data?.data ?? [];
    const tenantById = new Map(
      (tenantsDirectoryQuery.data?.tenants ?? []).map((t) => [
        String(t.tenant_id),
        t,
      ]),
    );
    return assignments
      .filter((a) => String(a.tier_id) === String(viewTier.id))
      .map((a) => ({
        tenantId: String(a.tenant_id),
        organisation:
          a.tenant_name ??
          tenantById.get(String(a.tenant_id))?.organisation ??
          `${INSTITUTION} ${a.tenant_id}`,
        budgetLimit: a.allocated_budget,
        effectiveFrom: a.budget_effective_from,
        effectiveTo: a.budget_effective_to,
      }));
  }, [viewTier, tenantTiersQuery.data, tenantsDirectoryQuery.data]);

  const isAssignedTenantsLoading =
    !!viewTierId &&
    (tenantTiersQuery.isLoading || tenantsDirectoryQuery.isLoading);

  // Services carry their tier mapping as an array of tier UUIDs (tierIds).
  // There's no server-side tier filter, so fetch all services and filter here.
  const servicesQuery = useQuery({
    queryKey: ["services-for-tiers", enabledTaskTypesParam ?? "all"],
    queryFn: () =>
      fetchAllServicesMatchingFilters({ taskTypes: enabledTaskTypesParam }),
    staleTime: 60 * 1000,
    enabled: !!viewTierId,
  });

  const servicesForViewTier = useMemo(() => {
    if (!viewTier) return [];
    const services = servicesQuery.data?.items ?? [];
    return services
      .filter(
        (s) =>
          (s.tierIds ?? []).includes(viewTier.id) ||
          (s.tierNames ?? []).includes(viewTier.name),
      )
      .map((s) => {
        const taskType =
          (typeof s.task === "object" && s.task && "type" in s.task
            ? s.task.type
            : undefined) ??
          s.task_type ??
          "";
        return {
          serviceId: s.serviceId ?? s.service_id ?? "",
          name: s.name,
          taskType,
          isPublished: !!s.isPublished,
        };
      });
  }, [viewTier, servicesQuery.data]);

  const isServicesForViewTierLoading = !!viewTierId && servicesQuery.isLoading;

  const filteredTiers = useMemo(() => {
    let result = tiers;
    if (filterTaskType) {
      result = result.filter((t) =>
        t.quotas.some(
          (q) => q.modelTaskType.toLowerCase() === filterTaskType.toLowerCase(),
        ),
      );
    }
    const q = searchQuery.trim().toLowerCase();
    if (q) {
      result = result.filter((t) => t.name.toLowerCase().includes(q));
    }
    return result;
  }, [tiers, searchQuery, filterTaskType]);

  const showTaskTypeAllOption = taskTypeNames.length > 1;
  const hasActiveFilters =
    searchQuery.trim() !== "" ||
    (showTaskTypeAllOption && filterTaskType !== "");

  const clearFilters = useCallback(() => {
    setSearchQuery("");
    setFilterTaskType(taskTypeNames.length === 1 ? taskTypeNames[0] : "");
  }, [taskTypeNames]);

  const refreshTiers = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: [TIER_QUERY_KEY] });
  }, [queryClient]);

  const handleDeleteClick = useCallback(
    (tier: Tier) => {
      setTierToDelete(tier);
      onDeleteOpen();
    },
    [onDeleteOpen],
  );

  const handleDeleteConfirm = useCallback(async () => {
    if (!checkSessionExpiry()) return;
    if (!tierToDelete?.id) return;
    setDeletingId(tierToDelete.id);
    try {
      await deleteTier(tierToDelete.id);
      toast({
        title: "Tier deleted",
        description: `"${tierToDelete.name}" has been deleted.`,
        status: "success",
        duration: 4000,
        isClosable: true,
      });
      refreshTiers();
    } catch (error: any) {
      const {
        title: errTitle,
        message: errMsg,
        showOnlyMessage,
      } = extractErrorInfo(error);
      toast({
        title: showOnlyMessage ? undefined : errTitle,
        description: errMsg,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setDeletingId(null);
      setTierToDelete(null);
      onDeleteClose();
    }
  }, [checkSessionExpiry, tierToDelete, toast, refreshTiers, onDeleteClose]);

  const handleOpenCreate = useCallback(() => {
    setFormData(defaultFormData());
    setShowQuotaErrors(false);
    onCreateOpen();
  }, [onCreateOpen]);

  const handleCreateSubmit = useCallback(async () => {
    if (!checkSessionExpiry()) return;
    if (!formData.name.trim()) {
      toast({
        title: "Tier name is required",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    if (formData.name.trim().length < 2) {
      toast({
        title: "Tier name must be at least 2 characters",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    const quotaError = validateQuotas(formData.quotas);
    if (quotaError) {
      setShowQuotaErrors(true);
      toast({
        title: quotaError,
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    setIsSubmitting(true);
    try {
      await createTier({
        name: formData.name.trim(),
        description: formData.description.trim() || undefined,
        quotas: formData.quotas.map((q) => ({
          modelTaskType: q.modelTaskType,
          limit: Number(q.limit),
        })),
      });
      toast({
        title: "Tier created",
        description: `"${formData.name.trim()}" has been created.`,
        status: "success",
        duration: 4000,
        isClosable: true,
      });
      onCreateClose();
      refreshTiers();
    } catch (error: any) {
      const {
        title: errTitle,
        message: errMsg,
        showOnlyMessage,
      } = extractErrorInfo(error);
      toast({
        title: showOnlyMessage ? undefined : errTitle,
        description: errMsg,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsSubmitting(false);
    }
  }, [checkSessionExpiry, formData, toast, onCreateClose, refreshTiers]);

  const handleOpenEdit = useCallback(
    (tier: Tier) => {
      if (!checkSessionExpiry()) return;
      setShowQuotaErrors(false);
      setEditingTier(tier);
      setFormData({
        name: tier.name,
        description: tier.description ?? "",
        quotas: tier.quotas?.length
          ? tier.quotas.map((q) => ({
              _key: generateUUID(),
              modelTaskType: q.modelTaskType,
              unit: q.unit || unitByTaskType[q.modelTaskType] || "",
              limit: String(q.limit),
              isExisting: true,
            }))
          : [newQuota()],
      });
      onEditOpen();
    },
    [checkSessionExpiry, onEditOpen, unitByTaskType],
  );

  const handleEditSubmit = useCallback(async () => {
    if (!checkSessionExpiry()) return;
    if (!formData.name.trim()) {
      toast({
        title: "Tier name is required",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    if (formData.name.trim().length < 2) {
      toast({
        title: "Tier name must be at least 2 characters",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    const quotaError = validateQuotas(formData.quotas);
    if (quotaError) {
      setShowQuotaErrors(true);
      toast({
        title: quotaError,
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    setIsSubmitting(true);
    try {
      await updateTier(editingTier!.id, {
        name: formData.name.trim(),
        description: formData.description.trim() || undefined,
        quotas: formData.quotas.map((q) => ({
          modelTaskType: q.modelTaskType,
          limit: Number(q.limit),
        })),
      });
      toast({
        title: "Tier updated",
        description: `"${formData.name.trim()}" has been updated.`,
        status: "success",
        duration: 4000,
        isClosable: true,
      });
      onEditClose();
      setEditingTier(null);
      refreshTiers();
    } catch (error: any) {
      const {
        title: errTitle,
        message: errMsg,
        showOnlyMessage,
      } = extractErrorInfo(error);
      toast({
        title: showOnlyMessage ? undefined : errTitle,
        description: errMsg,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsSubmitting(false);
    }
  }, [checkSessionExpiry, formData, toast, onEditClose, refreshTiers]);

  const handleRemoveQuota = useCallback(
    async (modelTaskType: string) => {
      if (!checkSessionExpiry()) return;
      if (!editingTier) return;
      const currentQuota = formData.quotas.find(
        (q) => q.modelTaskType === modelTaskType,
      );
      setRemovingTaskType(modelTaskType);
      try {
        await updateTier(editingTier.id, {
          name: editingTier.name,
          description: editingTier.description || undefined,
          quotas: currentQuota
            ? [{ modelTaskType, limit: Number(currentQuota.limit) }]
            : undefined,
        });
        setFormData((prev) => ({
          ...prev,
          quotas: prev.quotas.filter((q) => q.modelTaskType !== modelTaskType),
        }));
        toast({
          title: "Quota removed",
          description: `${modelTaskType} quota has been removed from this tier.`,
          status: "success",
          duration: 4000,
          isClosable: true,
        });
        refreshTiers();
      } catch (error: any) {
        const {
          title: errTitle,
          message: errMsg,
          showOnlyMessage,
        } = extractErrorInfo(error);
        toast({
          title: showOnlyMessage ? undefined : errTitle,
          description: errMsg,
          status: "error",
          duration: 5000,
          isClosable: true,
        });
      } finally {
        setRemovingTaskType(null);
      }
    },
    [checkSessionExpiry, editingTier, formData, toast, refreshTiers],
  );

  const handleOpenSchedule = useCallback(
    (quota: TierFormQuota) => {
      setScheduleTarget(quota);
      setScheduleLimit("");
      onScheduleOpen();
    },
    [onScheduleOpen],
  );

  const handleScheduleClose = useCallback(() => {
    onScheduleClose();
    setScheduleTarget(null);
    setScheduleLimit("");
  }, [onScheduleClose]);

  const handleScheduleConfirm = useCallback(async () => {
    if (!checkSessionExpiry()) return;
    if (!scheduleTarget || !editingTier) return;
    const newLimit = Number(scheduleLimit);
    if (!scheduleLimit || !Number.isFinite(newLimit) || newLimit <= 0) {
      toast({
        title: "Enter a valid quota limit",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    setIsScheduling(true);
    try {
      await updateTier(editingTier.id, {
        name: editingTier.name,
        description: editingTier.description || undefined,
        quotas: [
          { modelTaskType: scheduleTarget.modelTaskType, limit: newLimit },
        ],
      });
      toast({
        title: "Quota change scheduled",
        description: `${scheduleTarget.modelTaskType} quota change will take effect from the next billing cycle.`,
        status: "success",
        duration: 4000,
        isClosable: true,
      });
      handleScheduleClose();
      refreshTiers();
    } catch (error: any) {
      const {
        title: errTitle,
        message: errMsg,
        showOnlyMessage,
      } = extractErrorInfo(error);
      toast({
        title: showOnlyMessage ? undefined : errTitle,
        description: errMsg,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsScheduling(false);
    }
  }, [
    checkSessionExpiry,
    scheduleTarget,
    editingTier,
    scheduleLimit,
    formData,
    toast,
    handleScheduleClose,
    refreshTiers,
  ]);

  const handleViewClick = useCallback(
    (tier: Tier) => {
      setViewTierId(tier.id);
      onViewOpen();
    },
    [onViewOpen],
  );

  const handleCancelPendingQuota = useCallback(
    async (modelTaskType: string) => {
      if (!checkSessionExpiry()) return;
      if (!viewTier) return;
      setCancelingTaskType(modelTaskType);
      try {
        const currentQuota = viewTier.quotas.find(
          (q) => q.modelTaskType === modelTaskType,
        );
        await updateTier(viewTier.id, {
          name: viewTier.name,
          description: viewTier.description,
          quotas: currentQuota
            ? [{ modelTaskType, limit: currentQuota.limit }]
            : undefined,
          cancel_pending_quota: [modelTaskType],
        });
        toast({
          title: "Pending change canceled",
          description: `${modelTaskType} quota change has been canceled.`,
          status: "success",
          duration: 4000,
          isClosable: true,
        });
        refreshTiers();
      } catch (error: any) {
        const {
          title: errTitle,
          message: errMsg,
          showOnlyMessage,
        } = extractErrorInfo(error);
        toast({
          title: showOnlyMessage ? undefined : errTitle,
          description: errMsg,
          status: "error",
          duration: 5000,
          isClosable: true,
        });
      } finally {
        setCancelingTaskType(null);
      }
    },
    [checkSessionExpiry, viewTier, toast, refreshTiers],
  );

  return {
    // Search / filter
    searchQuery,
    setSearchQuery,
    filterTaskType,
    setFilterTaskType,
    hasActiveFilters,
    clearFilters,
    // Tiers data
    tiers,
    filteredTiers,
    isLoading: tiersQuery.isLoading,
    // Delete
    tierToDelete,
    deletingId,
    isDeleteOpen,
    onDeleteClose,
    handleDeleteClick,
    handleDeleteConfirm,
    // Create
    isCreateOpen,
    onCreateOpen,
    onCreateClose,
    handleOpenCreate,
    handleCreateSubmit,
    // Edit
    editingTier,
    isEditOpen,
    onEditClose,
    handleOpenEdit,
    handleEditSubmit,
    removingTaskType,
    handleRemoveQuota,
    // Schedule quota change
    scheduleTarget,
    scheduleLimit,
    setScheduleLimit,
    isScheduleOpen,
    isScheduling,
    handleOpenSchedule,
    handleScheduleClose,
    handleScheduleConfirm,
    // View
    viewTier,
    isViewOpen,
    onViewClose,
    handleViewClick,
    cancelingTaskType,
    handleCancelPendingQuota,
    assignedTenantsForViewTier,
    isAssignedTenantsLoading,
    servicesForViewTier,
    isServicesForViewTierLoading,
    // Shared form
    formData,
    setFormData,
    isSubmitting,
    showQuotaErrors,
    // Refs
    cancelRef,
  };
}
