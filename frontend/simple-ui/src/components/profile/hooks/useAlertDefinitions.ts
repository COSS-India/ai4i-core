import { useState, useMemo, useCallback } from "react";
import { useToast } from "@chakra-ui/react";
import alertingService from "../../../services/alertingService";
import type {
  AlertDefinition,
  AlertDefinitionCreate,
  AlertDefinitionUpdate,
  AlertAnnotation,
} from "../../../types/alerting";

const DEFAULT_THRESHOLD_UNIT = "percentage";

/** Map API alert_type (label or value) to form dropdown value */
const ALERT_TYPE_FORM_VALUES: Record<string, { value: string; label: string }[]> = {
  application: [
    { value: "latency", label: "Latency" },
    { value: "error_rate", label: "Error Rate" },
  ],
  infrastructure: [
    { value: "CPU", label: "CPU" },
    { value: "Memory", label: "Memory" },
    { value: "Disk", label: "Disk" },
  ],
};

function getAlertTypeFormValue(category: string, apiAlertType: string | null | undefined): string | null {
  if (apiAlertType == null || apiAlertType === "") return null;
  const types = ALERT_TYPE_FORM_VALUES[category] ?? ALERT_TYPE_FORM_VALUES.application;
  const found = types.find(
    (t) => t.value === apiAlertType || t.label === apiAlertType || t.value.toLowerCase() === apiAlertType.toLowerCase()
  );
  return found ? found.value : apiAlertType;
}

function getThresholdUnitFormValue(apiUnit: string | null | undefined): string {
  const u = (apiUnit ?? "").trim().toLowerCase();
  if (u === "seconds" || u === "percentage") return u;
  if (u === "percent") return "percentage";
  return DEFAULT_THRESHOLD_UNIT;
}

/** Allowed for_duration per evaluation_interval (for_duration must be >= eval interval). */
const FOR_DURATION_BY_EVAL: Record<string, string[]> = {
  "30s": ["1m", "2m", "5m"],
  "1m": ["2m", "5m", "10m"],
  "5m": ["5m", "10m"],
};

function normalizeForDuration(evalInterval: string | null | undefined, forDuration: string | null | undefined): string {
  const key = evalInterval ?? "30s";
  const allowed = FOR_DURATION_BY_EVAL[key] ?? FOR_DURATION_BY_EVAL["30s"];
  const cur = forDuration ?? "5m";
  return allowed.includes(cur) ? cur : allowed[0];
}

const EMPTY_CREATE_FORM: AlertDefinitionCreate = {
  name: "",
  promql_expr: "",
  category: "application",
  severity: "warning",
  urgency: "medium",
  alert_type: null,
  scope: DEFAULT_THRESHOLD_UNIT,
  evaluation_interval: "30s",
  for_duration: "5m",
  enabled: true,
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
  const [createErrors, setCreateErrors] = useState<Record<string, string>>({});

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
    setCreateErrors({});
    setIsCreateOpen(true);
  };
  const closeCreate = () => {
    setIsCreateOpen(false);
    setCreateForm(EMPTY_CREATE_FORM);
    setCreateAnnotations([]);
    setCreateErrors({});
  };

  /** Validate all required create-form fields; return errors keyed by field name */
  const validateCreateForm = useCallback(
    (form: AlertDefinitionCreate): Record<string, string> => {
      const errors: Record<string, string> = {};
      const nameTrimmed = (form.name ?? "").trim();
      if (!nameTrimmed) errors.name = "Name is required";
      const category = (form.category ?? "").trim();
      if (!category) errors.category = "Category is required";
      const severity = (form.severity ?? "").trim();
      if (!severity) errors.severity = "Severity is required";
      const alertType = (form.alert_type ?? "").trim();
      if (!alertType) errors.alert_type = "Alert type is required";
      const thresholdStr = (form.promql_expr ?? "").toString().trim();
      if (!thresholdStr) {
        errors.threshold_value = "Threshold value is required";
      } else {
        const num = Number(thresholdStr);
        if (Number.isNaN(num)) errors.threshold_value = "Enter a valid number";
        else if (num < 0) errors.threshold_value = "Must be 0 or greater";
      }
      return errors;
    },
    []
  );

  const handleCreate = async () => {
    setCreateErrors({});
    const errors = validateCreateForm(createForm);
    if (Object.keys(errors).length > 0) {
      setCreateErrors(errors);
      toast({
        title: "Validation Error",
        description: "Please fix the required fields below.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    const thresholdValue = Number(createForm.promql_expr);
    setIsCreating(true);
    try {
      const scope = createForm.scope;
      const thresholdUnit =
        typeof scope === "string" && scope.trim() !== ""
          ? scope.trim()
          : DEFAULT_THRESHOLD_UNIT;

      const payload = {
        name: createForm.name,
        description: createForm.description,
        category: createForm.category,
        severity: createForm.severity,
        urgency: createForm.urgency,
        alert_type: createForm.alert_type,
        evaluation_interval: createForm.evaluation_interval,
        for_duration: createForm.for_duration,
        threshold_value: thresholdValue,
        threshold_unit: thresholdUnit,
        enabled: createForm.enabled !== false,
      };
      await alertingService.createDefinition(payload as any);
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
    const category = item.category ?? "application";
    const thresholdValue =
      item.threshold_value != null && item.threshold_value !== undefined && !Number.isNaN(Number(item.threshold_value))
        ? String(item.threshold_value)
        : (item.promql_expr ?? "");
    const scope = getThresholdUnitFormValue(item.threshold_unit ?? item.scope);
    const alertType = getAlertTypeFormValue(category, item.alert_type);

    const evalInterval = item.evaluation_interval ?? "30s";
    const forDuration = normalizeForDuration(evalInterval, item.for_duration ?? "5m");
    setUpdateForm({
      description: item.description ?? "",
      promql_expr: thresholdValue,
      category,
      severity: item.severity ?? "warning",
      urgency: item.urgency ?? "medium",
      alert_type: alertType,
      scope,
      evaluation_interval: evalInterval,
      for_duration: forDuration,
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
      const payload: Record<string, unknown> = {};
      if (updateForm.description !== undefined) payload.description = updateForm.description;
      if (updateForm.category !== undefined) payload.category = updateForm.category;
      if (updateForm.severity !== undefined) payload.severity = updateForm.severity;
      if (updateForm.urgency !== undefined) payload.urgency = updateForm.urgency;
      if (updateForm.alert_type !== undefined) payload.alert_type = updateForm.alert_type;
      if (updateForm.evaluation_interval !== undefined) payload.evaluation_interval = updateForm.evaluation_interval;
      if (updateForm.for_duration !== undefined) payload.for_duration = updateForm.for_duration;
      if (updateForm.enabled !== undefined) payload.enabled = updateForm.enabled;

      if (updateForm.promql_expr !== undefined) {
        const thresholdValue = Number(updateForm.promql_expr);
        if (!Number.isNaN(thresholdValue)) {
          payload.threshold_value = thresholdValue;
        }
      }
      if (updateForm.scope !== undefined) {
        payload.threshold_unit = updateForm.scope;
      }

      await alertingService.updateDefinition(updateItem.id, payload as any);
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
    createErrors,
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
