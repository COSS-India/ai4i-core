import { useRouter } from "next/router";
import { useState, useEffect, useRef } from "react";
import type { TaskSpec } from "../../types/platform";
import { useAuth } from "../useAuth";
import { isRegistryReadOnlyUser } from "../../utils/rbac";
import { useSessionExpiry } from "../useSessionExpiry";
import { useToastWithDeduplication } from "../useToastWithDeduplication";
import { useAdminTableSurface } from "../../components/common/TableControls";
import { useModelsRegistry } from "./useModelsRegistry";
import { useModelCreate } from "./useModelCreate";
import { useModelDetail } from "./useModelDetail";
import { useModelStatusActions } from "./useModelStatusActions";
import type { Model } from "./shared";
import { initialFormData } from "./shared";

export type { Model } from "./shared";

export function useModelManagement() {
  const [formData, setFormData] = useState<Partial<Model>>(initialFormData);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState(0);

  const fetchModelsRef = useRef<(() => Promise<void>) | null>(null);
  const handleViewModelRef = useRef<((modelId: string) => Promise<void>) | null>(null);
  const openConfirmDialogRef = useRef<
    ((action: "deprecate" | "activate", model: Model) => void) | null
  >(null);

  const toast = useToastWithDeduplication();
  const { user } = useAuth();
  const isRegistryReadOnly = isRegistryReadOnlyUser(user?.roles);
  const viewTabIndex = isRegistryReadOnly ? 1 : 2;

  const { checkSessionExpiry } = useSessionExpiry();
  const router = useRouter();

  useEffect(() => {
    if (user?.roles?.includes("GUEST") || user?.roles?.includes("USER")) {
      toast({
        title: "Access Denied",
        description: "You do not have access to Model Management.",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      router.push("/");
    }
  }, [user, router, toast]);

  useEffect(() => {
    const t = router.query.tab;
    if (isRegistryReadOnly && (t === "1" || t === "create")) {
      setActiveTab(0);
      if (router.query.tab) {
        const q = { ...router.query } as Record<string, string>;
        delete q.tab;
        router.replace({ pathname: "/model-management", query: q }, undefined, { shallow: true });
      }
      return;
    }
    if (t === "2") setActiveTab(viewTabIndex);
    else if (t === "1") setActiveTab(1);
    else if (t !== "1" && t !== "2") setActiveTab(0);
  }, [router.query.tab, isRegistryReadOnly, router, viewTabIndex]);

  const pageContext = {
    router,
    isRegistryReadOnly,
    viewTabIndex,
    checkSessionExpiry,
  };

  const detail = useModelDetail({
    ...pageContext,
    fetchModelsRef,
    handleViewModelRef,
    setActiveTab,
  });

  const status = useModelStatusActions({
    ...pageContext,
    fetchModelsRef,
    openConfirmDialogRef,
    selectedModel: detail.selectedModel,
    setSelectedModel: detail.setSelectedModel,
    setUpdateFormData: detail.setUpdateFormData,
  });

  const registry = useModelsRegistry({
    handleViewModelRef,
    openConfirmDialogRef,
    updatingModelId: status.updatingModelId,
    isRegistryReadOnly,
  });

  fetchModelsRef.current = registry.fetchModels;

  const create = useModelCreate({
    ...pageContext,
    fetchModelsRef,
  });

  const { cardBg, borderColor: cardBorder } = useAdminTableSurface();

  const handleInputChange = (field: keyof Model, value: string | TaskSpec | string[]) => {
    setFormData((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  return {
    models: registry.models,
    isLoading: registry.isLoading,
    selectedModel: detail.selectedModel,
    isViewingModel: detail.isViewingModel,
    isEditingModel: detail.isEditingModel,
    formData,
    updateFormData: detail.updateFormData,
    isSubmitting,
    isUpdating: detail.isUpdating,
    activeTab,
    setActiveTab,
    uploadedModelData: create.uploadedModelData,
    parsedModelData: create.parsedModelData,
    validationErrors: create.validationErrors,
    isUploading: create.isUploading,
    isValidating: create.isValidating,
    uploadError: create.uploadError,
    updatingModelId: status.updatingModelId,
    modelIdsWithPublishedService: registry.modelIdsWithPublishedService,
    modelToConfirm: status.modelToConfirm,
    confirmAction: status.confirmAction,
    searchQuery: registry.searchQuery,
    setSearchQuery: registry.setSearchQuery,
    filterVersionStatus: registry.filterVersionStatus,
    setFilterVersionStatus: registry.setFilterVersionStatus,
    filterTaskType: registry.filterTaskType,
    setFilterTaskType: registry.setFilterTaskType,
    sortBy: registry.sortBy,
    nameSortDirection: registry.nameSortDirection,
    isConfirmOpen: status.isConfirmOpen,
    cancelConfirmRef: status.cancelConfirmRef,
    fileInputRef: create.fileInputRef,
    isRegistryReadOnly,
    viewTabIndex,
    router,
    cardBg,
    cardBorder,
    registryTableItems: registry.registryTableItems,
    hasActiveFilters: registry.hasActiveFilters,
    clearAllFilters: registry.clearAllFilters,
    handleInputChange,
    handleClearUpload: create.handleClearUpload,
    handleDownloadSample: create.handleDownloadSample,
    handleCreateModel: create.handleCreateModel,
    handleFileUpload: create.handleFileUpload,
    handleViewModel: detail.handleViewModel,
    handleUpdateModel: detail.handleUpdateModel,
    openConfirmDialog: status.openConfirmDialog,
    handleConfirmAction: status.handleConfirmAction,
    closeConfirmDialog: status.closeConfirmDialog,
    modelColumns: registry.modelColumns,
    setIsViewingModel: detail.setIsViewingModel,
    setSelectedModel: detail.setSelectedModel,
  };
}

export type UseModelManagementReturn = ReturnType<typeof useModelManagement>;
