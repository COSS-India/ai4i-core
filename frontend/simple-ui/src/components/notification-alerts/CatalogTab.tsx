import {
  Alert,
  AlertDescription,
  AlertIcon,
  Box,
  ListItem,
  Select,
  Text,
  UnorderedList,
  useDisclosure,
  VStack,
} from "@chakra-ui/react";
import React, { useMemo } from "react";
import { useNotificationCatalog } from "../../hooks/useNotificationCatalog";
import {
  SCOPE_LABELS,
  toThresholdDrafts,
  type CatalogScopeFilter,
  type NotificationAlertCatalogItem,
  type NotificationAlertType,
} from "../../types/notificationAlerts";
import { useToastWithDeduplication } from "../../utils/toast";
import { useDeferredColumnSort } from "../../utils/tableSort";
import DataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  type DataTableColumn,
} from "../common/table";
import ConfirmDialog from "../common/ConfirmDialog";
import FormActions from "../common/FormActions";
import { AdopterAdminCheckbox, ScopeToggle } from "./CatalogToolbar";
import ThresholdBandsCell from "./ThresholdBandsCell";

interface CatalogTabProps {
  type: NotificationAlertType;
  hint: string;
  nameColumnHeader: string;
  emptyMessage: string;
  entityLabel: string;
  showThresholds?: boolean;
}

const SCOPE_FILTER_OPTIONS: { label: string; value: CatalogScopeFilter }[] = [
  { label: "All scopes", value: "all" },
  { label: SCOPE_LABELS.GLOBAL, value: "GLOBAL" },
  { label: SCOPE_LABELS.INSTITUTION, value: "INSTITUTION" },
];

const CatalogTab: React.FC<CatalogTabProps> = ({
  type,
  hint,
  nameColumnHeader,
  emptyMessage,
  entityLabel,
  showThresholds = false,
}) => {
  const toast = useToastWithDeduplication();
  const confirmFlip = useDisclosure();
  const {
    items,
    filteredItems,
    search,
    setSearch,
    scopeFilter,
    setScopeFilter,
    isLoading,
    isSubmitting,
    error,
    getDraft,
    setScope,
    setAdminRecipient,
    setThresholds,
    discard,
    dirtyCount,
    pendingInstitutionFlips,
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
            <Text fontWeight="medium" fontSize="sm">
              {item.display_name}
            </Text>
            <Text fontSize="sm" color="ink.600" noOfLines={2}>
              {item.description}
            </Text>
          </VStack>
        ),
      },
      {
        id: "scope",
        header: "Scope",
        truncate: false,
        tdProps: { verticalAlign: "top" },
        cell: (item) => (
          <ScopeToggle
            value={getDraft(item).scope}
            rowLabel={item.display_name}
            onChange={(scope) => setScope(item.name, scope)}
          />
        ),
      },
      {
        id: "recipient",
        header: "Recipient",
        truncate: false,
        tdProps: { verticalAlign: "top" },
        cell: (item) => {
          const draft = getDraft(item);
          return (
            <AdopterAdminCheckbox
              isChecked={draft.adminRecipient}
              isDisabled={draft.scope === "INSTITUTION"}
              onChange={(checked) => setAdminRecipient(item.name, checked)}
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
        minWidth: "280px",
        tdProps: { verticalAlign: "top" },
        cell: (item) => (
          <ThresholdBandsCell
            bands={getDraft(item).thresholds ?? toThresholdDrafts(item.thresholds)}
            rowLabel={item.display_name}
            onApply={(bands) => setThresholds(item.name, bands)}
          />
        ),
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
        >
          <option value="EMAIL">Email</option>
        </Select>
      ),
    });

    return cols;
  }, [
    getDraft,
    nameColumnHeader,
    setAdminRecipient,
    setScope,
    setThresholds,
    showThresholds,
  ]);

  const runSubmit = async () => {
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

  const handleSubmit = () => {
    if (pendingInstitutionFlips.length > 0) {
      confirmFlip.onOpen();
      return;
    }
    void runSubmit();
  };

  const handleConfirmFlip = async () => {
    confirmFlip.onClose();
    await runSubmit();
  };

  const hasActiveFilters = search.trim() !== "" || scopeFilter !== "all";

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
        hasActiveFilters={hasActiveFilters}
        onClearFilters={() => {
          setSearch("");
          setScopeFilter("all");
        }}
        search={{
          value: search,
          onChange: setSearch,
          placeholder: "Search by name",
          fields: ["display_name", "name", "description"],
        }}
        filterDefs={[
          {
            id: "scope",
            label: "Scope",
            type: "select",
            value: scopeFilter,
            onChange: (value) => setScopeFilter(value as CatalogScopeFilter),
            options: SCOPE_FILTER_OPTIONS,
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
        onSubmit={handleSubmit}
        isLoading={isSubmitting}
        justify="flex-end"
        pt={4}
      />

      <ConfirmDialog
        isOpen={confirmFlip.isOpen}
        onClose={confirmFlip.onClose}
        onConfirm={handleConfirmFlip}
        title="Move to Institution scope?"
        confirmLabel="Submit"
        confirmColorScheme="orange"
        isConfirmLoading={isSubmitting}
        body={
          <VStack align="start" spacing={3}>
            <Text fontSize="sm">
              Every institution will be unsubscribed from the following and
              must opt in again to keep receiving them:
            </Text>
            <UnorderedList fontSize="sm" pl={2}>
              {pendingInstitutionFlips.map((item) => (
                <ListItem key={item.name}>{item.display_name}</ListItem>
              ))}
            </UnorderedList>
          </VStack>
        }
      />
    </Box>
  );
};

export default CatalogTab;
