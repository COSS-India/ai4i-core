import { useState, useMemo, useCallback } from "react";
import { useToast } from "@chakra-ui/react";
import alertingService from "../../../services/alertingService";
import type {
  AlertDefinition,
  AlertDefinitionCreate,
  AlertDefinitionUpdate,
  AlertAnnotation,
} from "../../../types/alerting";

const DEFAULT_THRESHOLD_UNIT = "%"; // overridden to "ms" when signal is latency

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
  description: null,
  category: "application",
  severity: "",
  urgency: "medium",
  sub_category: null,
  signal: null,
  signal_metric: null,
  condition_operator: null,
  threshold_value: null,
  threshold_unit: undefined,
  service: [],
  evaluation_interval: "30s",
  for_duration: "1m",
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
      if (!nameTrimmed) errors.name = "Alert name is required";
      const category = (form.category ?? "").trim();
      if (!category) errors.category = "Category is required";
      const severity = (form.severity ?? "").trim();
      if (!severity) errors.severity = "Severity is required";
      const subCategory = (form.sub_category ?? "").trim();
      if (!subCategory) errors.sub_category = "Subcategory is required";
      const signal = (form.signal ?? "").trim();
      if (!signal) errors.signal = "Signal is required";
      const signalMetric = (form.signal_metric ?? "").trim();
      if (!signalMetric) errors.signal_metric = "Signal metric is required";
      const conditionOp = (form.condition_operator ?? "").trim();
      if (!conditionOp) errors.condition_operator = "Condition is required";
      const thresholdVal = form.threshold_value;
      if (thresholdVal == null || (typeof thresholdVal === "number" && Number.isNaN(thresholdVal))) {
        errors.threshold_value = "Threshold value is required";
      } else if (typeof thresholdVal === "number" && thresholdVal < 0) {
        errors.threshold_value = "Must be 0 or greater";
      }
      const evalInterval = (form.evaluation_interval ?? "").trim();
      if (!evalInterval) errors.evaluation_interval = "Evaluation interval is required";
      const forDuration = (form.for_duration ?? "").trim();
      if (!forDuration) errors.for_duration = "For duration is required";
      // Infrastructure always targets all services; only validate service for application category
      if (form.category !== "infrastructure") {
        const serviceList = form.service ?? [];
        if (serviceList.length === 0) errors.service = "Select at least one target";
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

    const thresholdValue =
      typeof createForm.threshold_value === "number"
        ? createForm.threshold_value
        : Number(createForm.threshold_value);
    if (Number.isNaN(thresholdValue)) {
      setCreateErrors({ threshold_value: "Enter a valid number" });
      return;
    }

    setIsCreating(true);
    try {
      const serviceList = createForm.service ?? [];
      // Infrastructure always monitors all services — send empty array (backend treats as all)
      const isInfra = (createForm.category ?? "application") === "infrastructure";
      const hasAll = serviceList.includes("all");
      const servicePayload = isInfra || hasAll || serviceList.length === 0
        ? []
        : serviceList.filter((s) => s !== "all");

      const payload: AlertDefinitionCreate = {
        name: createForm.name.trim(),
        description: createForm.description?.trim() || null,
        category: createForm.category ?? "application",
        severity: createForm.severity,
        urgency: createForm.urgency ?? "medium",
        sub_category: createForm.sub_category ?? null,
        signal: createForm.signal ?? null,
        signal_metric: createForm.signal_metric ?? null,
        condition_operator: createForm.condition_operator ?? null,
        threshold_value: thresholdValue,
        threshold_unit: createForm.signal === "latency"
          ? (createForm.threshold_unit ?? "ms").trim()
          : "%",
        service: servicePayload.length > 0 ? servicePayload : undefined,
        evaluation_interval: createForm.evaluation_interval ?? "30s",
        for_duration: createForm.for_duration ?? "1m",
        enabled: createForm.enabled !== false,
        annotations: createForm.annotations?.length ? createForm.annotations : undefined,
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
    const category = item.category ?? "application";
    const evalInterval = item.evaluation_interval ?? "30s";
    const forDuration = normalizeForDuration(evalInterval, item.for_duration ?? "5m");
    setUpdateForm({
      description: item.description ?? "",
      category,
      severity: item.severity ?? "warning",
      urgency: item.urgency ?? "medium",
      sub_category: item.sub_category ?? undefined,
      signal: item.signal ?? undefined,
      signal_metric: item.signal_metric ?? undefined,
      condition_operator: item.condition_operator ?? undefined,
      threshold_value: item.threshold_value ?? undefined,
      threshold_unit: item.threshold_unit ?? undefined,
      service: item.service ?? undefined,
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
      const payload: AlertDefinitionUpdate = {};
      if (updateForm.description !== undefined) payload.description = updateForm.description;
      if (updateForm.category !== undefined) payload.category = updateForm.category;
      if (updateForm.severity !== undefined) payload.severity = updateForm.severity;
      if (updateForm.urgency !== undefined) payload.urgency = updateForm.urgency;
      if (updateForm.sub_category !== undefined) payload.sub_category = updateForm.sub_category;
      if (updateForm.signal !== undefined) payload.signal = updateForm.signal;
      if (updateForm.signal_metric !== undefined) payload.signal_metric = updateForm.signal_metric;
      if (updateForm.condition_operator !== undefined) payload.condition_operator = updateForm.condition_operator;
      if (updateForm.threshold_value !== undefined) payload.threshold_value = updateForm.threshold_value;
      if (updateForm.threshold_unit !== undefined) payload.threshold_unit = updateForm.threshold_unit;
      const svc = updateForm.service ?? [];
      if (updateForm.service !== undefined) {
        const list = svc.filter((s) => s !== "all");
        payload.service = list.length === 0 || svc.includes("all") ? [] : list;
      }
      if (updateForm.evaluation_interval !== undefined) payload.evaluation_interval = updateForm.evaluation_interval;
      if (updateForm.for_duration !== undefined) payload.for_duration = updateForm.for_duration;
      if (updateForm.enabled !== undefined) payload.enabled = updateForm.enabled;

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
