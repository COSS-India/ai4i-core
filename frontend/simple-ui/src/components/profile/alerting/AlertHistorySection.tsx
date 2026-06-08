// AlertHistorySection — extracted from AlertingTab

import React from "react";
import {
  AlertDialog,
  AlertDialogBody,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogOverlay,
  Badge,
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Checkbox,
  Divider,
  Drawer,
  DrawerBody,
  DrawerCloseButton,
  DrawerContent,
  DrawerFooter,
  DrawerHeader,
  DrawerOverlay,
  FormControl,
  FormErrorMessage,
  FormLabel,
  Heading,
  HStack,
  IconButton,
  Input,
  Menu,
  MenuButton,
  MenuDivider,
  MenuItem,
  MenuList,
  NumberDecrementStepper,
  NumberIncrementStepper,
  NumberInput,
  NumberInputField,
  NumberInputStepper,
  Radio,
  RadioGroup,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Tag,
  TagCloseButton,
  TagLabel,
  Text,
  Textarea,
  Tooltip,
  VStack,
  Wrap,
  WrapItem,
} from "@chakra-ui/react";
import { AddIcon, DeleteIcon, EditIcon, LockIcon, ViewIcon } from "@chakra-ui/icons";

import AdminDataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  TableSearchField,
  TableSelectField,
} from "../../common/AdminDataTable";
import StandardModal from "../../common/StandardModal";
import {
  CATEGORIES,
  CONDITION_OPERATORS,
  LATENCY_THRESHOLD_UNITS,
  PERCENTAGE_UNIT,
  RBAC_ROLES,
  SEVERITIES,
  SIGNAL_METRICS_BY_SIGNAL,
  SIGNALS_BY_SUB_CATEGORY,
  SUB_CATEGORIES_BY_CATEGORY,
  TARGET_SERVICES,
  URGENCIES,
} from "../../../types/alerting";
import {
  ALERT_TYPES_BY_CATEGORY,
  EVAL_INTERVALS,
  FOR_DURATIONS,
  FORM_REQUIRED_ASTERISK,
} from "./constants";
import { getAllowedForDurations } from "./utils";
import OptionSelector from "./OptionSelector";
import type { UseAlertingTabReturn } from "../hooks/useAlertingTab";


type Props = UseAlertingTabReturn;

export default function AlertHistorySection(tab: Props) {
  const {
    cardBg,
    cardBorder,
    defs,
    recvs,
    rules,
    history,
    defDeleteRef,
    recvDeleteRef,
    ruleDeleteRef,
    sortedDefinitions,
    sortedReceivers,
    sortedRules,
    sortedHistoryItems,
    definitionColumns,
    receiverColumns,
    routingRuleColumns,
    historyColumns,
    expandedUpdateServices,
    createRuleDef,
    setCreateRuleDef,
    createRuleScope,
    setCreateRuleScope,
    createRuleTenant,
    setCreateRuleTenant,
    createRuleErrors,
    setCreateRuleErrors,
    tenants,
    isLoadingTenants,
    editRuleCategory,
    setEditRuleCategory,
    editRuleSeverity,
    setEditRuleSeverity,
    editRuleDef,
    setEditRuleDef,
    editRuleScope,
    setEditRuleScope,
    editRuleErrors,
    setEditRuleErrors,
    resetCreateRuleExtras,
    resetEditRuleExtras,
    initEditRuleExtras,
    fetchTenants,
    validateAndCreate,
    activeAlertDefinitions,
    receiversSearchQuery,
    setReceiversSearchQuery,
    alertTypeLabel,
    formatThreshold,
    titleCase,
    categoryColor,
    severityColor,
  } = tab;

  return (
    <>
{/* Same shell + filter toolbar pattern as Alert Definitions (Card, toolbar, Clear all) */}
      <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
        <CardBody>
          <AdminDataTable
            items={sortedHistoryItems}
            columns={historyColumns}
            getRowKey={(row) => String(row.id)}
            onRowClick={history.openView}
            paginate="server"
            paginationPosition="top"
            pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
            initialPageSize={history.pageSize}
            serverPagination={{
              page: history.currentPage,
              pageSize: history.pageSize,
              totalItems: history.total,
              onPageChange: history.goToPage,
              onPageSizeChange: history.setPageSize,
            }}
            isLoading={history.isLoading}
            loadingMessage="Loading alert history..."
            emptyMessage="No alert history yet. Triggered alerts will appear here once your alerting pipeline records them."
            noResultsMessage="No entries match the current filters."
            hasActiveFilters={history.hasActiveFilters}
            onClearFilters={() => history.clearFilters()}
            filters={(
              <>
                <TableSearchField
                  value={history.searchQuery}
                  onChange={history.setSearchQuery}
                  placeholder="Search alerts..."
                  formControlProps={{ maxW: "260px" }}
                />
                <TableSelectField
                  label="Severity"
                  value={history.filterSeverity}
                  onChange={history.setFilterSeverity}
                  selectProps={{ maxW: "130px" }}
                >
                  <option value="all">Severity</option>
                  {SEVERITIES.map((s) => (
                    <option key={s} value={s}>{titleCase(s)}</option>
                  ))}
                </TableSelectField>
                <TableSelectField
                  label="Category"
                  value={history.filterCategory}
                  onChange={history.setFilterCategory}
                  selectProps={{ maxW: "140px" }}
                >
                  <option value="all">Category</option>
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>{titleCase(c)}</option>
                  ))}
                </TableSelectField>
                <HStack spacing={2} align="center" flexWrap="nowrap" flexShrink={0}>
                  <Text fontSize="xs" fontWeight="semibold" color="gray.600" whiteSpace="nowrap">
                    From
                  </Text>
                  <Input
                    type="date"
                    size="sm"
                    w="140px"
                    maxW="140px"
                    value={history.dateFrom}
                    onChange={(e) => history.setDateFrom(e.target.value)}
                    bg={cardBg}
                  />
                  <Text fontSize="xs" fontWeight="semibold" color="gray.600" whiteSpace="nowrap">
                    To
                  </Text>
                  <Input
                    type="date"
                    size="sm"
                    w="140px"
                    maxW="140px"
                    value={history.dateTo}
                    onChange={(e) => history.setDateTo(e.target.value)}
                    bg={cardBg}
                  />
                </HStack>
              </>
            )}
          />
        </CardBody>
      </Card>

      <StandardModal
        isOpen={history.isViewOpen}
        onClose={history.closeView}
        size="lg"
        title={
          <>
            <Text fontSize="lg" fontWeight="bold">Alert event</Text>
            {history.viewItem ? (
              <Text fontSize="sm" fontWeight="normal" color="gray.600" mt={1} noOfLines={2}>
                {history.viewItem.alert_name}
              </Text>
            ) : null}
          </>
        }
        headerProps={{ borderBottomWidth: "1px", borderColor: "gray.200" }}
        bodyProps={{ py: 6 }}
        footerProps={{ borderTopWidth: "1px", borderColor: "gray.200" }}
        footer={<Button onClick={history.closeView}>Close</Button>}
      >
        {history.viewItem ? (
          <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                {[
                  ["Category", titleCase(history.viewItem.category || "—")],
                  ["Severity", titleCase(history.viewItem.severity || "—")],
                  ["Status", (history.viewItem.status || "—").replace(/_/g, " ")],
                  ["Triggered", history.viewItem.triggered_at ?? "—"],
                  ["Resolved", history.viewItem.resolved_at ?? "—"],
                  ["Receiver", history.viewItem.receiver ?? "—"],
                  ["Notified", history.viewItem.notified_display || "—"],
                  ["Tenant", history.viewItem.tenant ?? "—"],
                  ["Recorded", history.viewItem.created_at ?? "—"],
                  ["Id", String(history.viewItem.id)],
                ].map(([label, val]) => (
                  <Box key={label}>
                    <Text fontSize="xs" fontWeight="bold" color="gray.500" textTransform="uppercase" letterSpacing="wider">
                      {label}
                    </Text>
                    <Text fontSize="sm" mt={1} wordBreak="break-word">{val}</Text>
                  </Box>
                ))}
          </SimpleGrid>
        ) : null}
      </StandardModal>
    </>
  );
}
