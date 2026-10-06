import { ChevronDownIcon } from "@chakra-ui/icons";
import {
  Alert,
  AlertDescription,
  AlertIcon,
  Box,
  Button,
  Checkbox,
  Heading,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
  Select,
  Text,
  VStack,
} from "@chakra-ui/react";
import React, { useMemo } from "react";
import { useMonitoringCatalog } from "../../hooks/useMonitoringCatalog";
import {
  MAX_MONITORING_PERCENT,
  MONITORING_RECIPIENT_LABELS,
  MONITORING_RECIPIENT_ROLES,
  MONITORING_UNIT_SUFFIX,
  monitoringUnitWord,
  validateMonitoringThresholdDrafts,
  type MonitoringCatalogItem,
  type MonitoringRecipientRole,
  type MonitoringThresholdDraftBand,
} from "../../types/notificationAlerts";
import { useToastWithDeduplication } from "../../utils/toast";
import { useDeferredColumnSort } from "../../utils/tableSort";
import DataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  type DataTableColumn,
} from "../common/table";
import FormActions from "../common/FormActions";
import ThresholdBandsCell from "./ThresholdBandsCell";

const EMPTY_MESSAGE = "No monitoring alerts match your search.";

const monitoringUnitSuffix = (band: MonitoringThresholdDraftBand) =>
  MONITORING_UNIT_SUFFIX[band.unit];

const monitoringBandUnitWord = (band: MonitoringThresholdDraftBand) =>
  monitoringUnitWord(band.unit);

/** The unit is fixed per alert, so the first band speaks for the row. */
function monitoringThresholdHint(item: MonitoringCatalogItem): string {
  const rule =
    item.monitoring_thresholds[0]?.unit === "PERCENT"
      ? `Greater than 0, up to ${MAX_MONITORING_PERCENT}%, no duplicates.`
      : "Greater than 0 seconds, no duplicates.";
  return `Check the thresholds that should fire and set each value. ${rule}`;
}

interface RecipientSelectProps {
  value: Record<MonitoringRecipientRole, boolean>;
  rowLabel: string;
  onChange: (roles: MonitoringRecipientRole[]) => void;
}

/** Adopter Admin / Moderator multi-select for one monitoring row. */
const RecipientSelect: React.FC<RecipientSelectProps> = ({
  value,
  rowLabel,
  onChange,
}) => {
  const selected = MONITORING_RECIPIENT_ROLES.filter((role) => value[role]);
  const label =
    selected.length > 0
      ? selected.map((role) => MONITORING_RECIPIENT_LABELS[role]).join(", ")
      : "None";

  const toggle = (role: MonitoringRecipientRole) =>
    onChange(
      MONITORING_RECIPIENT_ROLES.filter((r) => (r === role ? !value[r] : value[r])),
    );

  return (
    <Menu closeOnSelect={false} matchWidth>
      <MenuButton
        as={Button}
        rightIcon={<ChevronDownIcon />}
        variant="outline"
        size="sm"
        w="190px"
        textAlign="left"
        fontWeight="semibold"
        color={selected.length > 0 ? undefined : "ink.500"}
        aria-label={`Recipients for ${rowLabel}: ${label}`}
      >
        <Text as="span" noOfLines={1} display="block">
          {label}
        </Text>
      </MenuButton>
      <MenuList zIndex={10}>
        {MONITORING_RECIPIENT_ROLES.map((role) => {
          const checked = value[role];
          return (
            <MenuItem
              key={role}
              role="menuitemcheckbox"
              aria-checked={checked}
              onClick={() => toggle(role)}
              py={2}
            >
              {/* Display only — the MenuItem owns the click and keyboard
                  toggle, so the box must not take its own and flip twice. */}
              <Checkbox
                isChecked={checked}
                pointerEvents="none"
                tabIndex={-1}
                aria-hidden
                mr={3}
              />
              <Text fontSize="sm">{MONITORING_RECIPIENT_LABELS[role]}</Text>
            </MenuItem>
          );
        })}
      </MenuList>
    </Menu>
  );
};

/**
 * Adopter Admin editor for the MONITORING catalog rows (error rate /
 * latency). No scope column — monitoring alerts are platform-level.
 */
const MonitoringCatalogTab: React.FC = () => {
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
    setRecipients,
    setThresholds,
    discard,
    dirtyCount,
    submit,
  } = useMonitoringCatalog();

  const sortAccessors = useMemo(
    () => ({
      name: (item: MonitoringCatalogItem) => item.display_name ?? "",
    }),
    [],
  );
  const catalogSort = useDeferredColumnSort("name", sortAccessors);
  const sortedItems = useMemo(
    () => catalogSort.apply(filteredItems),
    [catalogSort, filteredItems],
  );

  const columns = useMemo(
    (): DataTableColumn<MonitoringCatalogItem>[] => [
      {
        id: "name",
        header: "Alert Name",
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
        id: "recipient",
        header: "Recipient",
        truncate: false,
        tdProps: { verticalAlign: "top" },
        cell: (item) => (
          <RecipientSelect
            value={getDraft(item).recipients}
            rowLabel={item.display_name}
            onChange={(roles) => setRecipients(item.name, roles)}
          />
        ),
      },
      {
        id: "thresholds",
        header: "Threshold Values",
        truncate: false,
        minWidth: "280px",
        tdProps: { verticalAlign: "top" },
        cell: (item) => (
          <ThresholdBandsCell
            bands={getDraft(item).thresholds}
            rowLabel={item.display_name}
            onApply={(bands) => setThresholds(item.name, bands)}
            validate={validateMonitoringThresholdDrafts}
            unitSuffix={monitoringUnitSuffix}
            unitWord={monitoringBandUnitWord}
            hint={monitoringThresholdHint(item)}
            inputMode="decimal"
            maxLength={6}
          />
        ),
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
    ],
    [getDraft, setRecipients, setThresholds],
  );

  const handleSubmit = async () => {
    const result = await submit();
    const saved = result.succeeded.length;

    if (result.failed) {
      toast({
        title:
          saved > 0
            ? `Partial save: ${saved} alert${saved > 1 ? "s" : ""} updated`
            : "Failed to save monitoring alerts",
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
        ? `${saved} alert${saved > 1 ? "s" : ""} updated`
        : "No changes to save",
      status: saved ? "success" : "info",
      duration: 3000,
      isClosable: true,
    });
  };

  return (
    <Box
      bg="white"
      borderWidth="1px"
      borderColor="ink.200"
      borderRadius="14px"
      pt={5}
    >
      <Box px={6} mb={4}>
        <Heading as="h2" size="sm" mb={1}>
          Monitoring Alerts Catalog
        </Heading>
        <Text color="ink.600" fontSize="sm" maxW="4xl">
          The standard, event-driven alerts for infrastructure monitoring
          available on the platform. Edit threshold values and select which
          ones should trigger an email alert. Choose whether each alert should
          notify the Adopter Admin, a Moderator, or both, then submit.
        </Text>
      </Box>

      <Box px={6} pb={6}>
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
          sort={catalogSort.sort}
          onSortChange={catalogSort.onSortChange}
          paginate="client"
          paginationPosition="bottom"
          pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
          isLoading={isLoading}
          loadingMessage="Loading monitoring alerts..."
          emptyMessage={EMPTY_MESSAGE}
          noResultsMessage={EMPTY_MESSAGE}
          unfilteredCount={items.length}
          hasActiveFilters={search.trim() !== ""}
          onClearFilters={() => setSearch("")}
          search={{
            value: search,
            onChange: setSearch,
            placeholder: "Search by name",
            fields: ["display_name", "name", "description"],
          }}
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
    </Box>
  );
};

export default MonitoringCatalogTab;
