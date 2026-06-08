// Services Management — thin composer wiring registry, create, and detail sub-hooks.

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/router";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../useAuth";
import { isRegistryReadOnlyUser } from "../../utils/rbac";
import { useSessionExpiry } from "../useSessionExpiry";
import { useToastWithDeduplication } from "../useToastWithDeduplication";
import { useAdminTableSurface } from "../../components/common/TableControls";
import type { FetchServicesRef, HandleViewServiceRef } from "./shared";
import { useServiceDetail } from "./useServiceDetail";
import { useServiceCreate } from "./useServiceCreate";
import { useServicesRegistry } from "./useServicesRegistry";

export function useServicesManagement() {
  const toast = useToastWithDeduplication();
  const { user } = useAuth();
  const isRegistryReadOnly = isRegistryReadOnlyUser(user?.roles);
  const viewTabIndex = isRegistryReadOnly ? 1 : 2;

  const router = useRouter();
  const queryClient = useQueryClient();
  const { checkSessionExpiry } = useSessionExpiry();
  const { cardBg, borderColor: cardBorder } = useAdminTableSurface();

  const [activeTab, setActiveTab] = useState(0);

  const fetchServicesRef = useRef<(() => Promise<void>) | null>(null) as FetchServicesRef;
  const handleViewServiceRef = useRef<((serviceId: string) => Promise<void>) | null>(
    null
  ) as HandleViewServiceRef;

  const pageContext = {
    router,
    queryClient,
    isRegistryReadOnly,
    viewTabIndex,
    checkSessionExpiry,
  };

  const detail = useServiceDetail({
    ...pageContext,
    fetchServicesRef,
    handleViewServiceRef,
    setActiveTab,
  });

  const registry = useServicesRegistry({
    ...pageContext,
    fetchServicesRef,
    handleViewServiceRef,
    selectedServiceSync: {
      selectedService: detail.selectedService,
      setSelectedService: detail.setSelectedService,
      setIsViewingService: detail.setIsViewingService,
      setSelectedServiceModelDeprecated: detail.setSelectedServiceModelDeprecated,
      setActiveTab,
    },
  });

  const create = useServiceCreate({
    ...pageContext,
    fetchServicesRef,
    setRegistryEpoch: registry.setRegistryEpoch,
    setActiveTab,
  });

  useEffect(() => {
    if (user?.roles?.includes("GUEST") || user?.roles?.includes("USER")) {
      toast({
        title: "Access Denied",
        description: "You do not have access to Services Management.",
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
      if (router.query.tab || router.query.modelId) {
        const q = { ...router.query } as Record<string, string>;
        delete q.tab;
        delete q.modelId;
        router.replace({ pathname: "/services-management", query: q }, undefined, { shallow: true });
      }
      return;
    }
    if (t === "2") setActiveTab(viewTabIndex);
    else if (t === "1" || t === "create") setActiveTab(1);
    else if (t !== "1" && t !== "2") setActiveTab(0);
  }, [router.query.tab, isRegistryReadOnly, router, viewTabIndex]);

  return {
    services: registry.services,
    models: create.models,
    isLoading: registry.isLoading,
    isLoadingModels: create.isLoadingModels,
    selectedService: detail.selectedService,
    setSelectedService: detail.setSelectedService,
    isViewingService: detail.isViewingService,
    setIsViewingService: detail.setIsViewingService,
    isEditingService: detail.isEditingService,
    formData: create.formData,
    updateFormData: detail.updateFormData,
    isSubmitting: create.isSubmitting,
    isUpdating: detail.isUpdating,
    deletingServiceUuid: registry.deletingServiceUuid,
    publishingServiceUuid: registry.publishingServiceUuid,
    unpublishingServiceUuid: registry.unpublishingServiceUuid,
    activeTab,
    setActiveTab,
    registryEpoch: registry.registryEpoch,
    searchQuery: registry.searchQuery,
    setSearchQuery: registry.setSearchQuery,
    filterStatus: registry.filterStatus,
    setFilterStatus: registry.setFilterStatus,
    filterTaskType: registry.filterTaskType,
    setFilterTaskType: registry.setFilterTaskType,
    sortBy: registry.sortBy,
    nameSortDirection: registry.nameSortDirection,
    confirmPublishService: registry.confirmPublishService,
    setConfirmPublishService: registry.setConfirmPublishService,
    confirmUnpublishService: registry.confirmUnpublishService,
    setConfirmUnpublishService: registry.setConfirmUnpublishService,
    selectedServiceModelDeprecated: detail.selectedServiceModelDeprecated,
    setSelectedServiceModelDeprecated: detail.setSelectedServiceModelDeprecated,
    isPublishConfirmOpen: registry.isPublishConfirmOpen,
    onPublishConfirmOpen: registry.onPublishConfirmOpen,
    onPublishConfirmClose: registry.onPublishConfirmClose,
    isUnpublishConfirmOpen: registry.isUnpublishConfirmOpen,
    onUnpublishConfirmOpen: registry.onUnpublishConfirmOpen,
    onUnpublishConfirmClose: registry.onUnpublishConfirmClose,
    cancelPublishRef: registry.cancelPublishRef,
    cancelUnpublishRef: registry.cancelUnpublishRef,
    isRegistryReadOnly,
    viewTabIndex,
    registryTableItems: registry.registryTableItems,
    hasActiveFilters: registry.hasActiveFilters,
    clearAllFilters: registry.clearAllFilters,
    router,
    isOpen: registry.isOpen,
    onClose: registry.onClose,
    cancelRef: registry.cancelRef,
    serviceToDelete: registry.serviceToDelete,
    preselectedModelFromQuery: create.preselectedModelFromQuery,
    setPreselectedModelFromQuery: create.setPreselectedModelFromQuery,
    cardBg,
    cardBorder,
    modelsForDropdown: create.modelsForDropdown,
    handleInputChange: create.handleInputChange,
    handleModelNameChange: create.handleModelNameChange,
    handleSubmit: create.handleSubmit,
    canCreateService: create.canCreateService,
    isCreateFormModelSelected: create.isCreateFormModelSelected,
    handleViewService: detail.handleViewService,
    handleUpdateService: detail.handleUpdateService,
    handlePublishConfirm: registry.handlePublishConfirm,
    handleUnpublishConfirm: registry.handleUnpublishConfirm,
    handleDeleteClick: registry.handleDeleteClick,
    handleDeleteConfirm: registry.handleDeleteConfirm,
    serviceColumns: registry.serviceColumns,
    resetCreateForm: create.resetCreateForm,
  };
}

export type UseServicesManagementReturn = ReturnType<typeof useServicesManagement>;
