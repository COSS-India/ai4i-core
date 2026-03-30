import { useState, useMemo, useCallback } from "react";
import { useToast } from "@chakra-ui/react";
import alertingService from "../../../services/alertingService";
import type {
  NotificationReceiver,
  NotificationReceiverCreate,
  NotificationReceiverUpdate,
} from "../../../types/alerting";

const EMPTY_CREATE_FORM: NotificationReceiverCreate = {
  category: "application",
  severity: "warning",
  alert_type: null,
  alert_names: null,
  tenant: null,
  rule_name: null,
  description: null,
  email_to: [],
  rbac_role: "ADMIN",
  email_subject_template: null,
  email_body_template: null,
};

export function useNotificationReceivers() {
  const toast = useToast();

  const [receivers, setReceivers] = useState<NotificationReceiver[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [filterEnabled, setFilterEnabled] = useState("all");

  // Create modal
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [createForm, setCreateForm] =
    useState<NotificationReceiverCreate>(EMPTY_CREATE_FORM);
  const [recipientMode, setRecipientMode] = useState<"email" | "role">(
    "email"
  );
  const [emailInput, setEmailInput] = useState("");

  // View modal
  const [isViewOpen, setIsViewOpen] = useState(false);
  const [viewItem, setViewItem] = useState<NotificationReceiver | null>(null);

  // Update modal
  const [isUpdateOpen, setIsUpdateOpen] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [updateItem, setUpdateItem] = useState<NotificationReceiver | null>(
    null
  );
  const [updateForm, setUpdateForm] = useState<NotificationReceiverUpdate>({});
  const [updateRecipientMode, setUpdateRecipientMode] = useState<
    "email" | "role"
  >("email");
  const [updateEmailInput, setUpdateEmailInput] = useState("");

  // Delete dialog
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteItem, setDeleteItem] = useState<NotificationReceiver | null>(
    null
  );

  const fetchReceivers = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await alertingService.listReceivers();
      setReceivers(data);
    } catch (error) {
      toast({
        title: "Error",
        description:
          error instanceof Error
            ? error.message
            : "Failed to load notification receivers",
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
    setRecipientMode("email");
    setEmailInput("");
    setIsCreateOpen(true);
  };
  const closeCreate = () => {
    setIsCreateOpen(false);
    setCreateForm(EMPTY_CREATE_FORM);
    setRecipientMode("email");
    setEmailInput("");
  };

  const addEmail = (email: string) => {
    const trimmed = email.trim();
    if (!trimmed) return;
    const current = createForm.email_to ?? [];
    if (!current.includes(trimmed)) {
      setCreateForm({ ...createForm, email_to: [...current, trimmed] });
    }
  };

  const removeEmail = (email: string) => {
    const current = createForm.email_to ?? [];
    setCreateForm({
      ...createForm,
      email_to: current.filter((e) => e !== email),
    });
  };

  const handleCreate = async () => {
    if (
      recipientMode === "email" &&
      (!createForm.email_to || createForm.email_to.length === 0)
    ) {
      toast({
        title: "Validation Error",
        description: "At least one email address is required",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    if (recipientMode === "role" && !createForm.rbac_role) {
      toast({
        title: "Validation Error",
        description: "Please select an RBAC role",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    setIsCreating(true);
    try {
      const payload: NotificationReceiverCreate = {
        category: createForm.category,
        severity: createForm.severity,
        ...(createForm.alert_type ? { alert_type: createForm.alert_type } : {}),
        ...(createForm.alert_names && createForm.alert_names.length > 0
          ? { alert_names: createForm.alert_names }
          : {}),
        ...(createForm.tenant ? { tenant: createForm.tenant } : {}),
        ...(createForm.rule_name ? { rule_name: createForm.rule_name } : {}),
        ...(createForm.description ? { description: createForm.description } : {}),
        ...(createForm.email_subject_template
          ? { email_subject_template: createForm.email_subject_template }
          : {}),
        ...(createForm.email_body_template
          ? { email_body_template: createForm.email_body_template }
          : {}),
      };
      if (recipientMode === "email") {
        payload.email_to = createForm.email_to;
      } else {
        payload.rbac_role = createForm.rbac_role;
      }
      await alertingService.createReceiver(payload);
      toast({
        title: "Notification Receiver Created",
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      closeCreate();
      await fetchReceivers();
    } catch (error) {
      toast({
        title: "Create Failed",
        description:
          error instanceof Error ? error.message : "Failed to create receiver",
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
    const mode = item.rbac_role ? "role" : "email";
    setUpdateRecipientMode(mode);
    setUpdateForm({
      rule_name: item.rule_name ?? undefined,
      description: item.description ?? undefined,
      category: item.category ?? undefined,
      severity: item.severity ?? undefined,
      alert_type: item.alert_type ?? undefined,
      alert_names: item.alert_names ?? undefined,
      tenant: item.tenant ?? undefined,
      email_to: item.email_to ?? [],
      rbac_role: item.rbac_role,
      email_subject_template: item.email_subject_template,
      email_body_template: item.email_body_template,
      enabled: item.enabled,
    });
    setUpdateEmailInput("");
    setIsUpdateOpen(true);
  };
  const closeUpdate = () => {
    setIsUpdateOpen(false);
    setUpdateItem(null);
    setUpdateForm({});
    setUpdateEmailInput("");
  };

  const addUpdateEmail = (email: string) => {
    const trimmed = email.trim();
    if (!trimmed) return;
    const current = updateForm.email_to ?? [];
    if (!current.includes(trimmed)) {
      setUpdateForm({ ...updateForm, email_to: [...current, trimmed] });
    }
  };

  const removeUpdateEmail = (email: string) => {
    const current = updateForm.email_to ?? [];
    setUpdateForm({
      ...updateForm,
      email_to: current.filter((e) => e !== email),
    });
  };

  const handleUpdate = async () => {
    if (!updateItem) return;
    setIsUpdating(true);
    try {
      const arraysEqual = (a: string[] | null | undefined, b: string[] | null | undefined) => {
        const aa = a ?? [];
        const bb = b ?? [];
        if (aa.length !== bb.length) return false;
        for (let i = 0; i < aa.length; i++) {
          if (aa[i] !== bb[i]) return false;
        }
        return true;
      };

      const normNullable = <T,>(v: T | null | undefined): T | null => (v === undefined ? null : v);

      const payload: NotificationReceiverUpdate = {};
      const old = updateItem;
      const next = updateForm;

      if (next.rule_name !== undefined) {
        const newVal = normNullable(next.rule_name);
        const oldVal = normNullable(old.rule_name);
        if (newVal !== oldVal) payload.rule_name = newVal;
      }
      if (next.description !== undefined) {
        const newVal = normNullable(next.description);
        const oldVal = normNullable(old.description);
        if (newVal !== oldVal) payload.description = newVal;
      }
      if (next.category !== undefined) {
        const newVal = normNullable(next.category);
        const oldVal = normNullable(old.category);
        if (newVal !== oldVal) payload.category = newVal;
      }
      if (next.severity !== undefined) {
        const newVal = normNullable(next.severity);
        const oldVal = normNullable(old.severity);
        if (newVal !== oldVal) payload.severity = newVal;
      }
      if (next.alert_type !== undefined) {
        const newVal = normNullable(next.alert_type);
        const oldVal = normNullable(old.alert_type);
        if (newVal !== oldVal) payload.alert_type = newVal;
      }
      if (next.alert_names !== undefined) {
        const newVal = next.alert_names ?? null;
        const oldVal = old.alert_names ?? null;
        const same = newVal == null && oldVal == null ? true : arraysEqual(newVal ?? [], oldVal ?? []);
        if (!same) payload.alert_names = newVal;
      }
      if (next.tenant !== undefined) {
        const newVal = normNullable(next.tenant);
        const oldVal = normNullable(old.tenant);
        if (newVal !== oldVal) payload.tenant = newVal;
      }
      if (next.email_subject_template !== undefined) {
        const newVal = normNullable(next.email_subject_template);
        const oldVal = normNullable(old.email_subject_template);
        if (newVal !== oldVal) payload.email_subject_template = newVal;
      }
      if (next.email_body_template !== undefined) {
        const newVal = normNullable(next.email_body_template);
        const oldVal = normNullable(old.email_body_template);
        if (newVal !== oldVal) payload.email_body_template = newVal;
      }

      if (next.enabled !== undefined && next.enabled !== old.enabled) {
        payload.enabled = next.enabled;
      }

      // Delivery mode: only include delivery fields if they differ from the original item.
      if (updateRecipientMode === "email") {
        const newEmailTo = next.email_to ?? [];
        if (!arraysEqual(newEmailTo, old.email_to)) payload.email_to = newEmailTo;

        // When switching to email mode, clear RBAC role only if it existed before.
        const oldRole = normNullable(old.rbac_role);
        if (oldRole !== null) payload.rbac_role = null;
      } else {
        // Role mode: only include rbac_role if it changed.
        const newRole = normNullable(next.rbac_role);
        const oldRole = normNullable(old.rbac_role);
        if (newRole !== oldRole) payload.rbac_role = newRole;
        // Keep existing email_to if the backend manages it based on rbac_role.
      }

      if (Object.keys(payload).length === 0) {
        toast({ title: "No changes", description: "Nothing to update.", status: "info", duration: 3000, isClosable: true });
        closeUpdate();
        return;
      }
      await alertingService.updateReceiver(updateItem.id, payload);
      toast({
        title: "Receiver Updated",
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      closeUpdate();
      await fetchReceivers();
    } catch (error) {
      toast({
        title: "Update Failed",
        description:
          error instanceof Error ? error.message : "Failed to update receiver",
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
      toast({
        title: "Receiver Deleted",
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      closeDelete();
      await fetchReceivers();
    } catch (error) {
      toast({
        title: "Delete Failed",
        description:
          error instanceof Error ? error.message : "Failed to delete receiver",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsDeleting(false);
    }
  };

  // ---- Filtering ----
  const filteredReceivers = useMemo(
    () =>
      [...receivers]
        .filter((r) => {
          if (filterEnabled === "enabled" && !r.enabled) return false;
          if (filterEnabled === "disabled" && r.enabled) return false;
          return true;
        })
        .sort(
          (a, b) =>
            new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        ),
    [receivers, filterEnabled]
  );

  return {
    receivers,
    filteredReceivers,
    isLoading,
    fetchReceivers,
    filterEnabled,
    setFilterEnabled,
    // Create
    isCreateOpen,
    isCreating,
    createForm,
    setCreateForm,
    recipientMode,
    setRecipientMode,
    emailInput,
    setEmailInput,
    addEmail,
    removeEmail,
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
    updateRecipientMode,
    setUpdateRecipientMode,
    updateEmailInput,
    setUpdateEmailInput,
    addUpdateEmail,
    removeUpdateEmail,
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
