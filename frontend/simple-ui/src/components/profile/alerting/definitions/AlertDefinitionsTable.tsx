// AlertDefinitionsTable

import React from "react";
import { Button, Card, CardBody } from "@chakra-ui/react";
import { AddIcon } from "@chakra-ui/icons";
import AdminDataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  TableSearchField,
  TableSelectField,
} from "../../../common/AdminDataTable";
import { CATEGORIES, SEVERITIES } from "../../../../types/alerting";
import type { DefinitionSectionProps } from "./types";

export default function AlertDefinitionsTable(tab: DefinitionSectionProps) {
  const {
    cardBg,
    cardBorder,
    defs,
    defDeleteRef,
    sortedDefinitions,
    definitionColumns,
    expandedUpdateServices,
    alertTypeLabel,
    formatThreshold,
    titleCase,
    categoryColor,
    severityColor,
  } = tab;

  return (
<Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
        <CardBody>
          <AdminDataTable
            items={sortedDefinitions}
            columns={definitionColumns}
            getRowKey={(d) => String(d.id)}
            onRowClick={defs.openView}
            paginate="client"
            pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
            isLoading={defs.isLoading}
            loadingMessage="Loading alert definitions..."
            emptyMessage="No alert definitions found. Click 'Create Alert Definition' to get started."
            noResultsMessage="No definitions match the current filters."
            unfilteredCount={defs.definitions.length}
            hasActiveFilters={
              !!defs.searchQuery.trim() ||
              defs.filterSeverity !== "all" ||
              defs.filterCategory !== "all" ||
              defs.filterEnabled !== "all"
            }
            onClearFilters={() => defs.resetFilters()}
            filterToolbarRightContent={(
              <Button
                size="sm"
                colorScheme="orange"
                leftIcon={<AddIcon />}
                onClick={defs.openCreate}
              >
                Create Alert Definition
              </Button>
            )}
            filters={(
              <>
                <TableSearchField
                  value={defs.searchQuery}
                  onChange={defs.setSearchQuery}
                  placeholder="Search alerts..."
                  formControlProps={{ maxW: "260px" }}
                />
                <TableSelectField
                  label="Severity"
                  value={defs.filterSeverity}
                  onChange={defs.setFilterSeverity}
                  selectProps={{ maxW: "130px" }}
                >
                  <option value="all">Severity</option>
                  {SEVERITIES.map((s) => (<option key={s} value={s}>{titleCase(s)}</option>))}
                </TableSelectField>
                <TableSelectField
                  label="Category"
                  value={defs.filterCategory}
                  onChange={defs.setFilterCategory}
                  selectProps={{ maxW: "140px" }}
                >
                  <option value="all">Category</option>
                  {CATEGORIES.map((c) => (<option key={c} value={c}>{titleCase(c)}</option>))}
                </TableSelectField>
                <TableSelectField
                  label="Status"
                  value={defs.filterEnabled}
                  onChange={defs.setFilterEnabled}
                  selectProps={{ maxW: "120px" }}
                >
                  <option value="all">Status</option>
                  <option value="enabled">Active</option>
                  <option value="disabled">Inactive</option>
                </TableSelectField>
              </>
            )}
          />
        </CardBody>
      </Card>
  );
}
