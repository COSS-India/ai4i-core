import { useState, useMemo, useCallback } from "react";
import { useToast } from "@chakra-ui/react";
import alertingService from "../../../services/alertingService";
import type {
  RoutingRule,
  RoutingRuleCreate,
  RoutingRuleUpdate,
  NotificationReceiver,
  NotificationReceiverCreate,
} from "../../../types/alerting";
import { DEFAULT_GROUP_BY } from "../../../types/alerting";

const EMPTY_CREATE_FORM: RoutingRuleCreate = {
  rule_name: "",
  receiver_id: 0,
  match_severity: "critical",
  match_category: "application",
  match_alert_type: null,
  group_by: [...DEFAULT_GROUP_BY],
  group_wait: "10s",
  group_interval: "10s",
  repeat_interval: "12h",
  continue_routing: false,
  priority: 100,
};

export function useRoutingRules() {
  const toast = useToast();

  const [rules, setRules] = useState<RoutingRule[]>([]);
  const [receivers, setReceivers] = useState<NotificationReceiver[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [filterEnabled, setFilterEnabled] = useState("all");
  const [filterRole, setFilterRole] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");

  // Create modal
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [createForm, setCreateForm] =
    useState<RoutingRuleCreate>(EMPTY_CREATE_FORM);

  // View modal
  const [isViewOpen, setIsViewOpen] = useState(false);
  const [viewItem, setViewItem] = useState<RoutingRule | null>(null);

  // Update modal
  const [isUpdateOpen, setIsUpdateOpen] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [updateItem, setUpdateItem] = useState<RoutingRule | null>(null);
  const [updateForm, setUpdateForm] = useState<RoutingRuleUpdate>({});

  // Delete dialog
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteItem, setDeleteItem] = useState<RoutingRule | null>(null);

  const fetchRules = useCallback(async () => {
    setIsLoading(true);
    try {
      const [rulesData, receiversData] = await Promise.all([
        alertingService.listRoutingRules(),
        alertingService.listReceivers(),
      ]);
      setRules(rulesData);
      setReceivers(receiversData);
    } catch (error) {
      toast({
        title: "Error",
        description:
          error instanceof Error
            ? error.message
            : "Failed to load routing rules",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsLoading(false);
    }
  }, [toast]);

  const getReceiverName = useCallback(
    (receiverId: number) => {
      const receiver = receivers.find((r) => r.id === receiverId);
      return receiver?.receiver_name ?? `Receiver #${receiverId}`;
    },
    [receivers]
  );

  // ---- Create ----
  const openCreate = () => {
    setCreateForm(EMPTY_CREATE_FORM);
    setIsCreateOpen(true);
  };
  const closeCreate = () => {
    setIsCreateOpen(false);
    setCreateForm(EMPTY_CREATE_FORM);
  };
  const handleCreate = async (selectedRole?: string) => {
    const ruleName = createForm.rule_name.trim();
    if (!ruleName) {
      toast({
        title: "Validation Error",
        description: "Rule name is required",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    if (!selectedRole?.trim()) {
      toast({
        title: "Validation Error",
        description: "Assign to Role is required",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    setIsCreating(true);
    try {
      // Single create path: create receiver by role only (backend auto-creates one routing rule).
      const receiverPayload: NotificationReceiverCreate = {
        category: createForm.match_category || "application",
        severity: createForm.match_severity || "critical",
        rbac_role: selectedRole.trim(),
      };
      if (createForm.match_alert_type) {
        receiverPayload.alert_type = createForm.match_alert_type;
      }
      const newReceiver = await alertingService.createReceiver(receiverPayload);

      // Find the auto-created routing rule for this receiver and set the user's rule name.
      const allRules = await alertingService.listRoutingRules();
      const autoCreatedRule = allRules.find((r) => r.receiver_id === newReceiver.id);
      if (autoCreatedRule) {
        await alertingService.updateRoutingRule(autoCreatedRule.id, {
          rule_name: ruleName,
        });
      }

      toast({
        title: "Routing Rule Created",
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      closeCreate();
      await fetchRules();
    } catch (error) {
      toast({
        title: "Create Failed",
        description:
          error instanceof Error
            ? error.message
            : "Failed to create routing rule",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsCreating(false);
    }
  };

  // ---- View ----
  const openView = (item: RoutingRule) => {
    setViewItem(item);
    setIsViewOpen(true);
  };
  const closeView = () => {
    setIsViewOpen(false);
    setViewItem(null);
  };

  // ---- Update ----
  const openUpdate = (item: RoutingRule) => {
    setUpdateItem(item);
    setUpdateForm({
      rule_name: item.rule_name,
      receiver_id: item.receiver_id,
      match_severity: item.match_severity,
      match_category: item.match_category,
      match_alert_type: item.match_alert_type,
      group_by: [...item.group_by],
      group_wait: item.group_wait,
      group_interval: item.group_interval,
      repeat_interval: item.repeat_interval,
      continue_routing: item.continue_routing,
      priority: item.priority,
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
      await alertingService.updateRoutingRule(updateItem.id, updateForm);
      toast({
        title: "Routing Rule Updated",
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      closeUpdate();
      await fetchRules();
    } catch (error) {
      toast({
        title: "Update Failed",
        description:
          error instanceof Error
            ? error.message
            : "Failed to update routing rule",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsUpdating(false);
    }
  };

  // ---- Delete ----
  const openDelete = (item: RoutingRule) => {
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
      await alertingService.deleteRoutingRule(deleteItem.id);
      toast({
        title: "Routing Rule Deleted",
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      closeDelete();
      await fetchRules();
    } catch (error) {
      toast({
        title: "Delete Failed",
        description:
          error instanceof Error
            ? error.message
            : "Failed to delete routing rule",
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
      [...rules]
        .filter((r) => {
          if (filterEnabled === "enabled" && !r.enabled) return false;
          if (filterEnabled === "disabled" && r.enabled) return false;
          if (searchQuery) {
            const q = searchQuery.toLowerCase();
            if (
              !r.rule_name.toLowerCase().includes(q) &&
              !(r.match_category ?? "").toLowerCase().includes(q) &&
              !(r.match_severity ?? "").toLowerCase().includes(q)
            ) return false;
          }
          return true;
        })
        .sort((a, b) => a.priority - b.priority),
    [rules, filterEnabled, searchQuery]
  );

  const getRuleForReceiver = useCallback(
    (receiverId: number) => rules.find((r) => r.receiver_id === receiverId),
    [rules]
  );

  const filteredReceivers = useMemo(
    () =>
      [...receivers].filter((rv) => {
        if (filterRole !== "all" && (rv.rbac_role ?? "") !== filterRole) return false;
        if (filterEnabled === "enabled" && !rv.enabled) return false;
        if (filterEnabled === "disabled" && rv.enabled) return false;
        if (searchQuery) {
          const q = searchQuery.toLowerCase();
          const linkedRule = rules.find((r) => r.receiver_id === rv.id);
          if (
            !rv.receiver_name.toLowerCase().includes(q) &&
            !(rv.rbac_role ?? "").toLowerCase().includes(q) &&
            !(linkedRule?.rule_name ?? "").toLowerCase().includes(q)
          ) return false;
        }
        return true;
      }),
    [receivers, rules, filterRole, filterEnabled, searchQuery]
  );

  return {
    rules,
    filteredRules,
    receivers,
    filteredReceivers,
    getRuleForReceiver,
    isLoading,
    fetchRules,
    getReceiverName,
    filterEnabled,
    setFilterEnabled,
    filterRole,
    setFilterRole,
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
