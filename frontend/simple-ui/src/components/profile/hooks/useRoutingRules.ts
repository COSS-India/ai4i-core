import { useState, useMemo, useCallback } from "react";
import { useToast } from "@chakra-ui/react";
import alertingService from "../../../services/alertingService";
import type {
  NotificationReceiver,
  NotificationReceiverCreate,
  NotificationReceiverUpdate,
} from "../../../types/alerting";

const EMPTY_CREATE_FORM = {
  rule_name: "",
  description: null as string | null,
  severity: null as string | null,
  category: null as string | null,
  alert_type: null as string | null,
  alert_names: null as string[] | null,
  tenant: null as string | null,
  email_to: [] as string[],
  rbac_role: "ADMIN" as string | null,
  email_subject_template: null as string | null,
  email_body_template: null as string | null,
};

type CreateForm = typeof EMPTY_CREATE_FORM;

type UpdateForm = {
  rule_name?: string | null;
  description?: string | null;
  category?: string | null;
  severity?: string | null;
  alert_type?: string | null;
  alert_names?: string[] | null;
  tenant?: string | null;
  email_to?: string[];
  rbac_role?: string | null;
  email_subject_template?: string | null;
  email_body_template?: string | null;
  enabled?: boolean;
};

export function useRoutingRules() {
  const toast = useToast();

  const [rules, setRules] = useState<NotificationReceiver[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [filterEnabled, setFilterEnabled] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");

  // Create modal
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [createForm, setCreateForm] = useState<CreateForm>({ ...EMPTY_CREATE_FORM });

  // View modal
  const [isViewOpen, setIsViewOpen] = useState(false);
  const [viewItem, setViewItem] = useState<NotificationReceiver | null>(null);

  // Update modal
  const [isUpdateOpen, setIsUpdateOpen] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [updateItem, setUpdateItem] = useState<NotificationReceiver | null>(null);
  const [updateForm, setUpdateForm] = useState<UpdateForm>({});

  // Delete dialog
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteItem, setDeleteItem] = useState<NotificationReceiver | null>(null);

  // ---- Fetch ----
  const fetchRules = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await alertingService.listReceivers();
      setRules(data);
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to load routing rules",
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
    setCreateForm({ ...EMPTY_CREATE_FORM });
    setIsCreateOpen(true);
  };
  const closeCreate = () => {
    setIsCreateOpen(false);
    setCreateForm({ ...EMPTY_CREATE_FORM });
  };
  const handleCreate = async (overrides?: Partial<CreateForm>) => {
    const form = overrides ? { ...createForm, ...overrides } : createForm;
    const hasEmail = form.email_to && form.email_to.length > 0;
    const hasRole = !!form.rbac_role;
    if (!hasEmail && !hasRole) {
      toast({ title: "Validation Error", description: "At least one email address or an RBAC role is required", status: "warning", duration: 3000, isClosable: true });
      return;
    }
    setIsCreating(true);
    try {
      const payload: NotificationReceiverCreate = {
        category: form.category || "application",
        severity: form.severity || "critical",
        ...(form.rule_name?.trim() ? { rule_name: form.rule_name.trim() } : {}),
        ...(form.description ? { description: form.description } : {}),
        ...(form.alert_type ? { alert_type: form.alert_type } : {}),
        ...(form.alert_names && form.alert_names.length > 0
          ? { alert_names: form.alert_names }
          : {}),
        ...(form.tenant ? { tenant: form.tenant } : {}),
        ...(form.email_subject_template
          ? { email_subject_template: form.email_subject_template }
          : {}),
        ...(form.email_body_template
          ? { email_body_template: form.email_body_template }
          : {}),
      };
      if (hasEmail) {
        payload.email_to = form.email_to;
      } else {
        payload.rbac_role = form.rbac_role;
      }
      await alertingService.createReceiver(payload);
      toast({ title: "Routing Rule Created", status: "success", duration: 3000, isClosable: true });
      closeCreate();
      await fetchRules();
    } catch (error) {
      toast({
        title: "Create Failed",
        description: error instanceof Error ? error.message : "Failed to create routing rule",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsCreating(false);
    }
  };

  // ---- View ----
  const openView = (item: NotificationReceiver) => {
    setViewItem(item);
    setIsViewOpen(true);
  };
  const closeView = () => {
    setIsViewOpen(false);
    setViewItem(null);
  };

  // ---- Update ----
  const openUpdate = (item: NotificationReceiver) => {
    setUpdateItem(item);
    setUpdateForm({
      rule_name: item.rule_name ?? null,
      description: item.description ?? null,
      category: item.category ?? null,
      severity: item.severity ?? null,
      alert_type: item.alert_type ?? null,
      alert_names: item.alert_names ?? null,
      tenant: item.tenant ?? null,
      email_to: item.email_to ?? [],
      rbac_role: item.rbac_role ?? null,
      email_subject_template: item.email_subject_template ?? null,
      email_body_template: item.email_body_template ?? null,
      enabled: item.enabled,
    });
    setIsUpdateOpen(true);
  };
  const closeUpdate = () => {
    setIsUpdateOpen(false);
    setUpdateItem(null);
    setUpdateForm({});
  };
  const handleUpdate = async (overrides?: UpdateForm) => {
    if (!updateItem) return;
    const nextForm = { ...updateForm, ...overrides };

    const arraysEqual = (a: string[] | null | undefined, b: string[] | null | undefined) => {
      const aa = a ?? [];
      const bb = b ?? [];
      if (aa.length !== bb.length) return false;
      for (let i = 0; i < aa.length; i++) {
        if (aa[i] !== bb[i]) return false;
      }
      return true;
    };

    const alertNamesEqual = (a: string[] | null | undefined, b: string[] | null | undefined) => {
      if (a == null && b == null) return true;
      if (a == null || b == null) return false;
      return arraysEqual(a, b);
    };

    setIsUpdating(true);
    try {
      const payload: NotificationReceiverUpdate = {};
      const old = updateItem;

      // Only include fields that actually changed vs the original item.
      if (nextForm.rule_name !== undefined) {
        const newVal = nextForm.rule_name ?? null;
        const oldVal = old.rule_name ?? null;
        if (newVal !== oldVal) payload.rule_name = newVal;
      }
      if (nextForm.description !== undefined) {
        const newVal = nextForm.description ?? null;
        const oldVal = old.description ?? null;
        if (newVal !== oldVal) payload.description = newVal;
      }
      if (nextForm.category !== undefined) {
        const newVal = nextForm.category ?? null;
        const oldVal = old.category ?? null;
        if (newVal !== oldVal) payload.category = newVal;
      }
      if (nextForm.severity !== undefined) {
        const newVal = nextForm.severity ?? null;
        const oldVal = old.severity ?? null;
        if (newVal !== oldVal) payload.severity = newVal;
      }
      if (nextForm.alert_type !== undefined) {
        const newVal = nextForm.alert_type ?? null;
        const oldVal = old.alert_type ?? null;
        if (newVal !== oldVal) payload.alert_type = newVal;
      }
      if (nextForm.alert_names !== undefined) {
        const newVal = nextForm.alert_names ?? null;
        const oldVal = old.alert_names ?? null;
        if (!alertNamesEqual(newVal, oldVal)) payload.alert_names = newVal;
      }
      if (nextForm.tenant !== undefined) {
        const newVal = nextForm.tenant ?? null;
        const oldVal = old.tenant ?? null;
        if (newVal !== oldVal) payload.tenant = newVal;
      }
      if (nextForm.email_subject_template !== undefined) {
        const newVal = nextForm.email_subject_template ?? null;
        const oldVal = old.email_subject_template ?? null;
        if (newVal !== oldVal) payload.email_subject_template = newVal;
      }
      if (nextForm.email_body_template !== undefined) {
        const newVal = nextForm.email_body_template ?? null;
        const oldVal = old.email_body_template ?? null;
        if (newVal !== oldVal) payload.email_body_template = newVal;
      }
      if (nextForm.enabled !== undefined) {
        if (nextForm.enabled !== old.enabled) payload.enabled = nextForm.enabled;
      }

      if (nextForm.email_to !== undefined) {
        const newVal = nextForm.email_to ?? [];
        const oldVal = old.email_to ?? [];
        if (!arraysEqual(newVal, oldVal)) payload.email_to = newVal;
      }
      if (nextForm.rbac_role !== undefined) {
        const newVal = nextForm.rbac_role ?? null;
        const oldVal = old.rbac_role ?? null;
        if (newVal !== oldVal) payload.rbac_role = newVal;
      }

      if (Object.keys(payload).length === 0) {
        toast({ title: "No changes", description: "Nothing to update.", status: "info", duration: 3000, isClosable: true });
        closeUpdate();
        return;
      }

      await alertingService.updateReceiver(updateItem.id, payload);
      toast({ title: "Routing Rule Updated", status: "success", duration: 3000, isClosable: true });
      closeUpdate();
      await fetchRules();
    } catch (error) {
      toast({
        title: "Update Failed",
        description: error instanceof Error ? error.message : "Failed to update routing rule",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsUpdating(false);
    }
  };

  // ---- Delete ----
  const openDelete = (item: NotificationReceiver) => {
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
      await alertingService.deleteReceiver(deleteItem.id);
      toast({ title: "Routing Rule Deleted", status: "success", duration: 3000, isClosable: true });
      closeDelete();
      await fetchRules();
    } catch (error) {
      toast({
        title: "Delete Failed",
        description: error instanceof Error ? error.message : "Failed to delete routing rule",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsDeleting(false);
    }
  };

  // ---- Filtering ----
  const filteredRules = useMemo(
    () =>
      [...rules].filter((r) => {
        if (filterEnabled === "enabled" && !r.enabled) return false;
        if (filterEnabled === "disabled" && r.enabled) return false;
        if (searchQuery) {
          const q = searchQuery.toLowerCase();
          const nameMatch = (r.rule_name ?? r.receiver_name ?? "").toLowerCase().includes(q);
          if (!nameMatch) return false;
        }
        return true;
      }),
    [rules, filterEnabled, searchQuery]
  );

  return {
    rules,
    filteredRules,
    isLoading,
    fetchRules,
    filterEnabled,
    setFilterEnabled,
    searchQuery,
    setSearchQuery,
    // Create
    isCreateOpen,
    isCreating,
    createForm,
    setCreateForm,
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
  };
}
