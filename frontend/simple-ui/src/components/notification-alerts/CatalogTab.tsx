import {
  Alert,
  AlertDescription,
  AlertIcon,
  Box,
  Flex,
  Select,
  Text,
  VStack,
} from "@chakra-ui/react";
import React, { useMemo } from "react";
import { useNotificationCatalog } from "../../hooks/useNotificationCatalog";
import {
  toThresholdDrafts,
  type NotificationAlertCatalogItem,
  type NotificationAlertType,
} from "../../types/notificationAlerts";
import { useToastWithDeduplication } from "../../utils/toast";
import { useDeferredColumnSort } from "../../utils/tableSort";
import DataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  type DataTableColumn,
} from "../common/table";
import FormActions from "../common/FormActions";
import { RecipientRoleCheckboxes } from "./CatalogToolbar";
import ThresholdBandsCell from "./ThresholdBandsCell";

interface CatalogTabProps {
  type: NotificationAlertType;
  hint: string;
  nameColumnHeader: string;
  emptyMessage: string;
  entityLabel: string;
  showThresholds?: boolean;
}

const CatalogTab: React.FC<CatalogTabProps> = ({
  type,
  hint,
  nameColumnHeader,
  emptyMessage,
  entityLabel,
  showThresholds = false,
}) => {
  const toast = useToastWithDeduplication();
  const {
    items,
    filteredItems,
    search,
    setSearch,
    isLoading,
    isSubmitting,
    error,
    getDraft,
    setRecipientRole,
    setThresholds,
    dirtyCount,
    submit,
  } = useNotificationCatalog(type);

  const catalogSortAccessors = useMemo(
    () => ({
      name: (item: NotificationAlertCatalogItem) => item.display_name ?? "",
    }),
    [],
  );
  const catalogSort = useDeferredColumnSort("name", catalogSortAccessors);
  const sortedItems = useMemo(
    () => catalogSort.apply(filteredItems),
    [catalogSort, filteredItems],
  );

  const columns = useMemo((): DataTableColumn<NotificationAlertCatalogItem>[] => {
    const cols: DataTableColumn<NotificationAlertCatalogItem>[] = [
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
            <Flex align="center" gap={2} flexWrap="wrap">
              <Text fontWeight="medium" fontSize="sm">
                {item.display_name}
              </Text>
            </Flex>
            <Text fontSize="sm" color="ink.600" noOfLines={2}>
              {item.description}
            </Text>
          </VStack>
        ),
      },
      {
        id: "recipientRole",
        header: "Recipient Role",
        truncate: false,
        tdProps: { verticalAlign: "top" },
        cell: (item) => {
          const draft = getDraft(item);
          return (
            <RecipientRoleCheckboxes
              tenantChecked={draft.recipient_roles["TENANT ADMIN"]}
              adopterChecked={draft.recipient_roles.ADMIN}
              onTenantChange={(checked) =>
                setRecipientRole(item.name, "TENANT ADMIN", checked)
              }
              onAdopterChange={(checked) =>
                setRecipientRole(item.name, "ADMIN", checked)
              }
            />
          );
        },
      },
      {
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
          >
            <option value="EMAIL">Email</option>
          </Select>
        ),
      },
    ];

    if (showThresholds) {
      cols.push({
        id: "thresholds",
        header: "Thresholds",
        truncate: false,
        minWidth: "200px",
        tdProps: { verticalAlign: "top" },
        cell: (item) => {
          const draft = getDraft(item);
          return (
            <ThresholdBandsCell
              bands={draft.thresholds ?? toThresholdDrafts(item.thresholds)}
              rowLabel={item.display_name}
              onApply={(bands) => setThresholds(item.name, bands)}
            />
          );
        },
      });
    }

    return cols;
  }, [
    getDraft,
    nameColumnHeader,
    setRecipientRole,
    setThresholds,
    showThresholds,
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

  return (
    <Box>
      {error ? (
        <Alert status="error" borderRadius="md" mb={3}>
          <AlertIcon />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <Text color="ink.600" fontSize="sm" mb={4}>
        {hint}
      </Text>

      <DataTable
        layout="admin"
        items={sortedItems}
        columns={columns}
        getRowKey={(item) => item.name}
        sort={catalogSort.sort}
        onSortChange={catalogSort.onSortChange}
        paginate="client"
        paginationPosition="bottom"
        pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
        isLoading={isLoading}
        loadingMessage={`Loading ${entityLabel}s...`}
        emptyMessage={emptyMessage}
        noResultsMessage={emptyMessage}
        unfilteredCount={items.length}
        hasActiveFilters={search.trim() !== ""}
        onClearFilters={() => setSearch("")}
        search={{
          value: search,
          onChange: setSearch,
          placeholder: "Search by name",
          fields: ["display_name", "name", "description"],
        }}
      />

      <FormActions
        submitLabel={dirtyCount > 0 ? `Submit (${dirtyCount})` : "Submit"}
        hideCancel
        onSubmit={() => void handleSubmit()}
        isLoading={isSubmitting}
        justify="flex-end"
        pt={4}
      />
    </Box>
  );
};

export default CatalogTab;
