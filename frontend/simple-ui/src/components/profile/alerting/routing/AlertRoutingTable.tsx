// AlertRoutingTable

import React from "react";
import { Box, Button } from "@chakra-ui/react";
import { AddIcon } from "@chakra-ui/icons";
import AdminDataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  TableSearchField,
  TableSelectField,
} from "../../../common/AdminDataTable";
import type { RoutingSectionProps } from "./types";

export default function AlertRoutingTable(tab: RoutingSectionProps) {
  const {
    cardBg,
    cardBorder,
    defs,
    rules,
    ruleDeleteRef,
    sortedRules,
    routingRuleColumns,
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
    fetchTenants,
    validateAndCreate,
    activeAlertDefinitions,
    titleCase,
    categoryColor,
    severityColor,
  } = tab;

  return (
<Box bg={cardBg} borderColor={cardBorder} borderWidth="1px" borderRadius="lg" p={4}>
        <AdminDataTable
          items={sortedRules}
          columns={routingRuleColumns}
          getRowKey={(rule) => String(rule.id)}
          onRowClick={(rule) => {
            defs.fetchDefinitions();
            rules.openView(rule);
          }}
          paginate="client"
          pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
          isLoading={rules.isLoading}
          loadingMessage="Loading alert routing..."
          emptyMessage="No alert routing configured. Click 'Create Routing Rule' to add one."
          noResultsMessage="No entries match the current filters."
          unfilteredCount={rules.rules.length}
          hasActiveFilters={!!rules.searchQuery.trim() || rules.filterEnabled !== "all"}
          onClearFilters={() => {
            rules.setSearchQuery("");
            rules.setFilterEnabled("all");
          }}
          filterToolbarRightContent={(
            <Button
              size="sm"
              colorScheme="orange"
              leftIcon={<AddIcon />}
              onClick={() => { resetCreateRuleExtras(); defs.fetchDefinitions(); fetchTenants(); rules.openCreate(); }}
            >
              Create Routing Rule
            </Button>
          )}
          filters={(
            <>
              <TableSearchField
                value={rules.searchQuery}
                onChange={rules.setSearchQuery}
                placeholder="Search routing rules..."
                formControlProps={{ maxW: "280px" }}
              />
              <TableSelectField
                label="Status"
                value={rules.filterEnabled}
                onChange={rules.setFilterEnabled}
                selectProps={{ maxW: "120px" }}
              >
                <option value="all">Status</option>
                <option value="enabled">Active</option>
                <option value="disabled">Inactive</option>
              </TableSelectField>
            </>
          )}
        />
      </Box>
  );
}
