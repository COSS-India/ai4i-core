import { useState, useMemo, useCallback } from "react";
import { useToast } from "@chakra-ui/react";
import alertingService from "../../../services/alertingService";
import type {
  AlertDefinition,
  AlertDefinitionCreate,
  AlertDefinitionUpdate,
  AlertAnnotation,
} from "../../../types/alerting";

const EMPTY_CREATE_FORM: AlertDefinitionCreate = {
  name: "",
  promql_expr: "",
  category: "application",
  severity: "warning",
  urgency: "medium",
  alert_type: null,
  scope: null,
  evaluation_interval: "30s",
  for_duration: "5m",
  annotations: [],
};

const EMPTY_UPDATE_FORM: AlertDefinitionUpdate = {};

export function useAlertDefinitions() {
  const toast = useToast();

  const [definitions, setDefinitions] = useState<AlertDefinition[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterSeverity, setFilterSeverity] = useState("all");
  const [filterCategory, setFilterCategory] = useState("all");
  const [filterEnabled, setFilterEnabled] = useState("all");

  // Create modal
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [createForm, setCreateForm] =
    useState<AlertDefinitionCreate>(EMPTY_CREATE_FORM);
  const [createAnnotations, setCreateAnnotations] = useState<AlertAnnotation[]>(
    []
  );

  // View modal
  const [isViewOpen, setIsViewOpen] = useState(false);
  const [viewItem, setViewItem] = useState<AlertDefinition | null>(null);

  // Update modal
  const [isUpdateOpen, setIsUpdateOpen] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [updateItem, setUpdateItem] = useState<AlertDefinition | null>(null);
  const [updateForm, setUpdateForm] =
    useState<AlertDefinitionUpdate>(EMPTY_UPDATE_FORM);
  const [updateAnnotations, setUpdateAnnotations] = useState<
    AlertAnnotation[]
  >([]);

  // Delete dialog
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteItem, setDeleteItem] = useState<AlertDefinition | null>(null);

  // Toggle enabled
  const [togglingId, setTogglingId] = useState<number | null>(null);

  const fetchDefinitions = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await alertingService.listDefinitions();
      setDefinitions(data);
    } catch (error) {
      toast({
        title: "Error",
        description:
          error instanceof Error
            ? error.message
            : "Failed to load alert definitions",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsLoading(false);
    }
  }, [toast]);

  // ---- Create ----
  const openCreate = () => {
    setCreateForm(EMPTY_CREATE_FORM);
    setCreateAnnotations([]);
    setIsCreateOpen(true);
  };
  const closeCreate = () => {
    setIsCreateOpen(false);
    setCreateForm(EMPTY_CREATE_FORM);
    setCreateAnnotations([]);
  };
  const handleCreate = async () => {
    if (!createForm.name.trim() || !createForm.promql_expr.trim()) {
      toast({
        title: "Validation Error",
        description: "Name and PromQL expression are required",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    setIsCreating(true);
    try {
      const payload: AlertDefinitionCreate = {
        ...createForm,
        annotations:
          createAnnotations.length > 0 ? createAnnotations : undefined,
      };
      await alertingService.createDefinition(payload);
      toast({
        title: "Alert Definition Created",
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      closeCreate();
      await fetchDefinitions();
    } catch (error) {
      toast({
        title: "Create Failed",
        description:
          error instanceof Error ? error.message : "Failed to create definition",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsCreating(false);
    }
  };

  // ---- View ----
  const openView = (item: AlertDefinition) => {
    setViewItem(item);
    setIsViewOpen(true);
  };
  const closeView = () => {
    setIsViewOpen(false);
    setViewItem(null);
  };

  // ---- Update ----
  const openUpdate = (item: AlertDefinition) => {
    setUpdateItem(item);
    setUpdateForm({
      description: item.description ?? "",
      promql_expr: item.promql_expr,
      category: item.category,
      severity: item.severity,
      urgency: item.urgency,
      alert_type: item.alert_type,
      scope: item.scope,
      evaluation_interval: item.evaluation_interval,
      for_duration: item.for_duration,
      enabled: item.enabled,
    });
    setUpdateAnnotations(item.annotations ? [...item.annotations] : []);
    setIsUpdateOpen(true);
  };
  const closeUpdate = () => {
    setIsUpdateOpen(false);
    setUpdateItem(null);
    setUpdateForm(EMPTY_UPDATE_FORM);
    setUpdateAnnotations([]);
  };
  const handleUpdate = async () => {
    if (!updateItem) return;
    setIsUpdating(true);
    try {
      const payload: AlertDefinitionUpdate = {
        ...updateForm,
        annotations:
          updateAnnotations.length > 0 ? updateAnnotations : undefined,
      };
      await alertingService.updateDefinition(updateItem.id, payload);
      toast({
        title: "Alert Definition Updated",
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      closeUpdate();
      await fetchDefinitions();
    } catch (error) {
      toast({
        title: "Update Failed",
        description:
          error instanceof Error ? error.message : "Failed to update definition",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsUpdating(false);
    }
  };

  // ---- Delete ----
  const openDelete = (item: AlertDefinition) => {
    setDeleteItem(item);
    setIsDeleteOpen(true);
  };
  const closeDelete = () => {
    setIsDeleteOpen(false);
    setDeleteItem(null);
  };
  const handleDelete = async () => {
    if (!deleteItem) return;
    setIsDeleting(true);
    try {
      await alertingService.deleteDefinition(deleteItem.id);
      toast({
        title: "Alert Definition Deleted",
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      closeDelete();
      await fetchDefinitions();
    } catch (error) {
      toast({
        title: "Delete Failed",
        description:
          error instanceof Error ? error.message : "Failed to delete definition",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsDeleting(false);
    }
  };

  // ---- Toggle enabled ----
  const handleToggleEnabled = async (item: AlertDefinition) => {
    setTogglingId(item.id);
    try {
      await alertingService.toggleDefinitionEnabled(item.id, !item.enabled);
      toast({
        title: item.enabled ? "Alert Disabled" : "Alert Enabled",
        status: "success",
        duration: 2000,
        isClosable: true,
      });
      await fetchDefinitions();
    } catch (error) {
      toast({
        title: "Toggle Failed",
        description:
          error instanceof Error ? error.message : "Failed to toggle alert",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setTogglingId(null);
    }
  };

  // ---- Filtering ----
  const filteredDefinitions = useMemo(
    () =>
      [...definitions]
        .filter((d) => {
          if (searchQuery.trim()) {
            const q = searchQuery.toLowerCase();
            const matchesSearch =
              d.name.toLowerCase().includes(q) ||
              (d.description ?? "").toLowerCase().includes(q) ||
              (d.alert_type ?? "").toLowerCase().includes(q) ||
              d.promql_expr.toLowerCase().includes(q);
            if (!matchesSearch) return false;
          }
          if (filterSeverity !== "all" && d.severity !== filterSeverity)
            return false;
          if (filterCategory !== "all" && d.category !== filterCategory)
            return false;
          if (filterEnabled === "enabled" && !d.enabled) return false;
          if (filterEnabled === "disabled" && d.enabled) return false;
          return true;
        })
        .sort(
          (a, b) =>
            new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        ),
    [definitions, searchQuery, filterSeverity, filterCategory, filterEnabled]
  );

  const resetFilters = () => {
    setSearchQuery("");
    setFilterSeverity("all");
    setFilterCategory("all");
    setFilterEnabled("all");
  };

  return {
    definitions,
    filteredDefinitions,
    isLoading,
    fetchDefinitions,
    // Search & Filters
    searchQuery,
    setSearchQuery,
    filterSeverity,
    setFilterSeverity,
    filterCategory,
    setFilterCategory,
    filterEnabled,
    setFilterEnabled,
    resetFilters,
    // Create
    isCreateOpen,
    isCreating,
    createForm,
    setCreateForm,
    createAnnotations,
    setCreateAnnotations,
    openCreate,
    closeCreate,
    handleCreate,
    // View
    isViewOpen,
    viewItem,
    openView,
    closeView,
    // Update
    isUpdateOpen,
    isUpdating,
    updateItem,
    updateForm,
    setUpdateForm,
    updateAnnotations,
    setUpdateAnnotations,
    openUpdate,
    closeUpdate,
    handleUpdate,
    // Delete
    isDeleteOpen,
    isDeleting,
    deleteItem,
    openDelete,
    closeDelete,
    handleDelete,
    // Toggle
    togglingId,
    handleToggleEnabled,
  };
}
