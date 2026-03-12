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
  severity: null as string | null,
  category: null as string | null,
  tenant: null as string | null,
};

type CreateForm = typeof EMPTY_CREATE_FORM;

type UpdateForm = {
  rule_name?: string;
  category?: string | null;
  severity?: string | null;
  alert_names?: string[] | null;
  tenant?: string | null;
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
    const ruleName = form.rule_name.trim();
    if (!ruleName) {
      toast({ title: "Validation Error", description: "Rule name is required", status: "warning", duration: 3000, isClosable: true });
      return;
    }
    setIsCreating(true);
    try {
      const payload: NotificationReceiverCreate = {
        rule_name: ruleName,
        category: form.category || "application",
        severity: form.severity || "critical",
        rbac_role: "ADMIN",
        ...(form.tenant ? { tenant: form.tenant } : {}),
      };
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
      rule_name: item.rule_name ?? "",
      category: item.category ?? null,
      severity: item.severity ?? null,
      alert_names: item.alert_names ?? null,
      tenant: item.tenant ?? null,
      enabled: item.enabled,
    });
    setIsUpdateOpen(true);
  };
  const closeUpdate = () => {
    setIsUpdateOpen(false);
    setUpdateItem(null);
    setUpdateForm({});
  };
  const handleUpdate = async () => {
    if (!updateItem) return;
    setIsUpdating(true);
    try {
      const payload: NotificationReceiverUpdate = {};
      if (updateForm.rule_name !== undefined) payload.rule_name = updateForm.rule_name;
      if (updateForm.category !== undefined) payload.category = updateForm.category ?? null;
      if (updateForm.severity !== undefined) payload.severity = updateForm.severity ?? null;
      if (updateForm.alert_names !== undefined) payload.alert_names = updateForm.alert_names ?? null;
      if (updateForm.tenant !== undefined) payload.tenant = updateForm.tenant ?? null;
      if (updateForm.enabled !== undefined) payload.enabled = updateForm.enabled;
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
          const defMatch = (r.alert_names ?? []).some((n) => n.toLowerCase().includes(q));
          if (!nameMatch && !defMatch) return false;
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
