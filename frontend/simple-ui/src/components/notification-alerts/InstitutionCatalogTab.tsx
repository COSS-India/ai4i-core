import {
  Alert,
  AlertDescription,
  AlertIcon,
  Box,
  Select,
  Text,
  VStack,
} from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import React, { useCallback, useMemo } from "react";
import { INSTITUTION, INSTITUTION_ARTICLE } from "../../config/constants";
import { useAuth } from "../../hooks/useAuth";
import { catalogErrorMessage } from "../../hooks/useNotificationCatalog";
import { useNotificationSubscriptions } from "../../hooks/useNotificationSubscriptions";
import { listAllUsers } from "../../services/tenantService";
import type {
  NotificationAlertType,
  NotificationSubscriptionItem,
  SubscriptionStatusFilter,
} from "../../types/notificationAlerts";
import { getTenantIdFromToken } from "../../utils/helpers";
import { isTenantAdminUser } from "../../utils/rbac";
import { useToastWithDeduplication } from "../../utils/toast";
import { useDeferredColumnSort } from "../../utils/tableSort";
import DataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  type DataTableColumn,
} from "../common/table";
import FormActions from "../common/FormActions";
import { RecipientsPicker, SubscriptionToggle, ThresholdChips } from "./SubscriptionControls";

interface InstitutionCatalogTabProps {
  type: NotificationAlertType;
  nameColumnHeader: string;
  emptyMessage: string;
  entityLabel: string;
  showThresholds?: boolean;
}

const STATUS_FILTER_OPTIONS: { label: string; value: SubscriptionStatusFilter }[] = [
  { label: "All statuses", value: "all" },
  { label: "Mandatory", value: "mandatory" },
  { label: "Subscribed", value: "subscribed" },
  { label: "Unsubscribed", value: "unsubscribed" },
];

/**
 * Institution Admin's view of one catalog type: subscribe/unsubscribe the
 * optional rows and pick extra recipients from their own institution.
 * Mandatory (GLOBAL) rows are shown locked.
 */
const InstitutionCatalogTab: React.FC<InstitutionCatalogTabProps> = ({
  type,
  nameColumnHeader,
  emptyMessage,
  entityLabel,
  showThresholds = false,
}) => {
  const toast = useToastWithDeduplication();
  const { user } = useAuth();
  const tenantId = useMemo(
    () => user?.tenant_id?.trim() || getTenantIdFromToken() || null,
    [user?.tenant_id],
  );
  const currentUserId = user?.user_id;

  const {
    items,
    filteredItems,
    search,
    setSearch,
    statusFilter,
    setStatusFilter,
    isLoading,
    isSubmitting,
    error,
    getDraft,
    setSubscribed,
    setRecipients,
    discard,
    dirtyCount,
    submit,
  } = useNotificationSubscriptions(type, tenantId);

  const usersQuery = useQuery({
    queryKey: ["tenant-users", tenantId],
    queryFn: () => listAllUsers(tenantId as string),
    enabled: Boolean(tenantId),
    staleTime: 60_000,
  });

  // Every Institution Admin is already emailed for every subscribed row
  // (the send path adds them unconditionally), so they are neither offered
  // nor counted as "added". The seed migration still wrote the admin's own
  // id into every row's `recipients`; those ids are kept as-is on save.
  const alreadyNotifiedIds = useMemo(() => {
    const ids = new Set<string>();
    if (currentUserId) ids.add(currentUserId);
    (usersQuery.data?.users ?? []).forEach((u) => {
      if (isTenantAdminUser(u.roles)) ids.add(u.user_id);
    });
    return ids;
  }, [currentUserId, usersQuery.data]);

  const pickableUsers = useMemo(
    () =>
      (usersQuery.data?.users ?? []).filter(
        (u) => u.is_active && !alreadyNotifiedIds.has(u.user_id),
      ),
    [alreadyNotifiedIds, usersQuery.data],
  );

  // Loaded on mount so the "N added" counts are right, and re-fetched every
  // time a drawer opens so a user added in Institution Management shows up
  // without a page reload.
  const { refetch: refetchUsers } = usersQuery;
  const reloadUsers = useCallback(() => {
    void refetchUsers();
  }, [refetchUsers]);

  const usersError = usersQuery.isError
    ? catalogErrorMessage(usersQuery.error, "Couldn't load people.")
    : null;
  const onlyAdminsLeft =
    pickableUsers.length === 0 &&
    (usersQuery.data?.users ?? []).some(
      (u) => u.is_active && alreadyNotifiedIds.has(u.user_id) && u.user_id !== currentUserId,
    );

  const sortAccessors = useMemo(
    () => ({
      name: (item: NotificationSubscriptionItem) => item.display_name ?? "",
    }),
    [],
  );
  const sort = useDeferredColumnSort("name", sortAccessors);
  const sortedItems = useMemo(() => sort.apply(filteredItems), [sort, filteredItems]);

  const columns = useMemo((): DataTableColumn<NotificationSubscriptionItem>[] => {
    const cols: DataTableColumn<NotificationSubscriptionItem>[] = [
      {
        id: "name",
        header: nameColumnHeader,
        sortable: true,
        sortAccessor: (item) => item.display_name ?? "",
        truncate: false,
        minWidth: "240px",
        tdProps: { verticalAlign: "top" },
        cell: (item) => (
          <VStack align="start" spacing={1}>
            <Text fontWeight="medium" fontSize="sm">
              {item.display_name}
            </Text>
            {item.description ? (
              <Text fontSize="sm" color="ink.600" noOfLines={2}>
                {item.description}
              </Text>
            ) : null}
          </VStack>
        ),
      },
      {
        id: "subscription",
        header: "My emails",
        truncate: false,
        tdProps: { verticalAlign: "top" },
        cell: (item) => (
          <SubscriptionToggle
            subscribed={getDraft(item).subscribed}
            locked={item.locked}
            rowLabel={item.display_name}
            onChange={(subscribed) => setSubscribed(item.name, subscribed)}
          />
        ),
      },
      {
        id: "recipients",
        header: "Also Notify In Your Org",
        truncate: false,
        tdProps: { verticalAlign: "top" },
        cell: (item) => {
          const draft = getDraft(item);
          return (
            <RecipientsPicker
              value={draft.recipients}
              onChange={(recipients) => setRecipients(item.name, recipients)}
              users={pickableUsers}
              alreadyNotifiedIds={alreadyNotifiedIds}
              isLoadingUsers={usersQuery.isFetching}
              usersError={usersError}
              onlyAdminsLeft={onlyAdminsLeft}
              onOpen={reloadUsers}
              isDisabled={!item.locked && !draft.subscribed}
              rowLabel={item.display_name}
              channel={item.channels[0] ?? "EMAIL"}
            />
          );
        },
      },
    ];

    if (showThresholds) {
      cols.push({
        id: "thresholds",
        header: "Threshold Values",
        truncate: false,
        tdProps: { verticalAlign: "top" },
        cell: (item) => <ThresholdChips bands={item.thresholds} />,
      });
    }

    cols.push({
      id: "channel",
      header: "Delivery Channel",
      truncate: false,
      tdProps: { verticalAlign: "top" },
      cell: (item) => (
        <Select
          value={item.channels[0] ?? "EMAIL"}
          isDisabled
          maxW="140px"
          size="sm"
          bg="ink.50"
          aria-label={`Delivery channel for ${item.display_name}`}
        >
          <option value="EMAIL">Email</option>
        </Select>
      ),
    });

    return cols;
  }, [
    getDraft,
    nameColumnHeader,
    alreadyNotifiedIds,
    onlyAdminsLeft,
    pickableUsers,
    reloadUsers,
    usersError,
    setRecipients,
    setSubscribed,
    showThresholds,
    usersQuery.isFetching,
  ]);

  const handleSubmit = async () => {
    const result = await submit();
    const saved = result.succeeded.length;

    if (result.failed) {
      toast({
        title:
          saved > 0
            ? `Partial save: ${saved} ${entityLabel}${saved > 1 ? "s" : ""} updated`
            : `Failed to save ${entityLabel}s`,
        description:
          saved > 0
            ? `Saved: ${result.succeeded.join(", ")}. Failed on '${result.failed.name}': ${result.failed.message}`
            : result.failed.message,
        status: saved > 0 ? "warning" : "error",
        duration: 6000,
        isClosable: true,
      });
      return;
    }

    toast({
      title: saved
        ? `${saved} ${entityLabel}${saved > 1 ? "s" : ""} updated`
        : "No changes to save",
      status: saved ? "success" : "info",
      duration: 3000,
      isClosable: true,
    });
  };

  if (!tenantId) {
    return (
      <Alert status="warning" borderRadius="md">
        <AlertIcon />
        <AlertDescription>
          {`Your account isn't linked to ${INSTITUTION_ARTICLE} ${INSTITUTION.toLowerCase()}, so there are no subscriptions to manage.`}
        </AlertDescription>
      </Alert>
    );
  }

  const hasActiveFilters = search.trim() !== "" || statusFilter !== "all";

  return (
    <Box>
      {error ? (
        <Alert status="error" borderRadius="md" mb={3}>
          <AlertIcon />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <DataTable
        layout="admin"
        items={sortedItems}
        columns={columns}
        getRowKey={(item) => item.name}
        sort={sort.sort}
        onSortChange={sort.onSortChange}
        paginate="client"
        paginationPosition="bottom"
        pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
        isLoading={isLoading}
        loadingMessage={`Loading ${entityLabel}s...`}
        emptyMessage={emptyMessage}
        noResultsMessage={emptyMessage}
        unfilteredCount={items.length}
        hasActiveFilters={hasActiveFilters}
        onClearFilters={() => {
          setSearch("");
          setStatusFilter("all");
        }}
        search={{
          value: search,
          onChange: setSearch,
          placeholder: "Search by name",
          fields: ["display_name", "name", "description"],
        }}
        filterDefs={[
          {
            id: "status",
            label: "Status",
            type: "select",
            value: statusFilter,
            onChange: (value) => setStatusFilter(value as SubscriptionStatusFilter),
            options: STATUS_FILTER_OPTIONS,
            width: { base: "full", sm: "160px" },
          },
        ]}
        filterToolbarRightContent={
          isLoading ? null : (
            <Text fontSize="sm" color="ink.600" whiteSpace="nowrap">
              {filteredItems.length} of {items.length} shown
            </Text>
          )
        }
      />

      <FormActions
        submitLabel={dirtyCount > 0 ? `Submit (${dirtyCount})` : "Submit"}
        cancelLabel="Discard changes"
        onCancel={dirtyCount > 0 ? discard : undefined}
        onSubmit={() => void handleSubmit()}
        isLoading={isSubmitting}
        isDisabled={dirtyCount === 0}
        justify="flex-end"
        pt={4}
      />
    </Box>
  );
};

export default InstitutionCatalogTab;
