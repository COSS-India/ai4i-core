import { useState, useCallback, useMemo, useRef } from "react";
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
  type Tier,
} from "../services/tierManagementService";
import { useInferenceTypes } from "./useInferenceTypes";
import type { TierFormData, TierFormQuota } from "../types/tierManagement";

const TIER_QUERY_KEY = "tiers";

function newQuota(): TierFormQuota {
  return {
    _key: crypto.randomUUID(),
    modelTaskType: "",
    unit: "",
    limit: "",
  };
}

function defaultFormData(): TierFormData {
  return { name: "", description: "", quotas: [newQuota()] };
}

export function useTierManagement() {
  const toast = useToastWithDeduplication();
  const queryClient = useQueryClient();
  const { checkSessionExpiry } = useSessionExpiry();
  const { unitByTaskType } = useInferenceTypes();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterTaskType, setFilterTaskType] = useState("");

  const [tierToDelete, setTierToDelete] = useState<Tier | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const [viewTier, setViewTier] = useState<Tier | null>(null);
  const [formData, setFormData] = useState<TierFormData>(defaultFormData);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [editingTier, setEditingTier] = useState<Tier | null>(null);

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

  const tiersQuery = useQuery({
    queryKey: [TIER_QUERY_KEY, filterTaskType],
    queryFn: () => fetchTiers(filterTaskType || undefined),
    staleTime: 30 * 1000,
    retry: 1,
  });

  const tiers = tiersQuery.data?.data ?? [];

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

  const hasActiveFilters = searchQuery.trim() !== "" || filterTaskType !== "";

  const clearFilters = useCallback(() => {
    setSearchQuery("");
    setFilterTaskType("");
  }, []);

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
    const invalidQuota = formData.quotas.find(
      (q) => !q.modelTaskType || !q.limit,
    );
    if (invalidQuota) {
      toast({
        title: "Each quota must have a task type and limit",
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
      setEditingTier(tier);
      setFormData({
        name: tier.name,
        description: tier.description ?? "",
        quotas: tier.quotas?.length
          ? tier.quotas.map((q) => ({
              _key: crypto.randomUUID(),
              modelTaskType: q.modelTaskType,
              unit: q.unit || unitByTaskType[q.modelTaskType] || "",
              limit: String(q.limit),
            }))
          : [newQuota()],
      });
      onEditOpen();
    },
    [checkSessionExpiry, onEditOpen],
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

  const handleViewClick = useCallback(
    (tier: Tier) => {
      setViewTier(tier);
      onViewOpen();
    },
    [onViewOpen],
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
    // View
    viewTier,
    isViewOpen,
    onViewClose,
    handleViewClick,
    // Shared form
    formData,
    setFormData,
    isSubmitting,
    // Refs
    cancelRef,
  };
}
