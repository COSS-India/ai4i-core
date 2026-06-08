import {
  Alert,
  AlertIcon,
  Badge,
  Box,
  Button,
  Card,
  CardBody,
  HStack,
  VStack,
} from "@chakra-ui/react";
import { AddIcon } from "@chakra-ui/icons";
import AdminDataTable, { TableSearchField, TableSelectField } from "../common/AdminDataTable";
import type { PolicyOut } from "../../services/policyService";
import type { UsePoliciesPanelReturn } from "./hooks/usePoliciesPanel";

type Props = UsePoliciesPanelReturn;

export default function PoliciesTable(p: Props) {
  const {
    error,
    cardBg,
    borderColor,
    tableEpoch,
    filteredPolicies,
    policyColumns,
    searchQuery,
    setSearchQuery,
    filterActive,
    setFilterActive,
    filterGlobal,
    setFilterGlobal,
    hasActiveFilters,
    clearAllFilters,
    bumpTablePage,
    openCreate,
    loading,
    allPolicies,
    openPolicyView,
  } = p;

  return (
    <Box>
      {error && (
        <Alert status="error" mb={4} borderRadius="md">
          <AlertIcon />
          {error}
        </Alert>
      )}

      <Card bg={cardBg} borderWidth="1px" borderColor={borderColor} borderRadius="lg" boxShadow="none">
        <CardBody>
          <AdminDataTable<PolicyOut>
            key={tableEpoch}
            items={filteredPolicies}
            columns={policyColumns}
            getRowKey={(row) => row.policy_id}
            filters={
              <VStack align="stretch" spacing={3} flex="1" w="full">
                <HStack spacing={3} align="flex-end" flexWrap="wrap" rowGap={3} w="full">
                  <TableSearchField
                    label="Search"
                    value={searchQuery}
                    onChange={setSearchQuery}
                    placeholder="Search by policy name…"
                    formControlProps={{ w: { base: "full", md: "280px" } }}
                    inputProps={{ pl: 10 }}
                  />
                  <TableSelectField
                    label="Active"
                    value={filterActive}
                    onChange={setFilterActive}
                    formControlProps={{ w: { base: "full", sm: "140px" } }}
                  >
                    <option value="">All</option>
                    <option value="true">Active</option>
                    <option value="false">Inactive</option>
                  </TableSelectField>
                  <TableSelectField
                    label="Scope"
                    value={filterGlobal}
                    onChange={setFilterGlobal}
                    formControlProps={{ w: { base: "full", sm: "160px" } }}
                  >
                    <option value="">All</option>
                    <option value="true">Global</option>
                    <option value="false">Tenant-scoped</option>
                  </TableSelectField>
                  <Box flex="1" minW={0} />
                </HStack>
                {hasActiveFilters ? (
                  <HStack spacing={2} flexWrap="wrap">
                    {searchQuery.trim() ? (
                      <Badge
                        colorScheme="blue"
                        fontSize="xs"
                        px={2}
                        py={1}
                        cursor="pointer"
                        onClick={() => {
                          setSearchQuery("");
                          bumpTablePage();
                        }}
                        _hover={{ opacity: 0.8 }}
                      >
                        Search: &quot;{searchQuery.trim()}&quot; ×
                      </Badge>
                    ) : null}
                    {filterActive ? (
                      <Badge
                        colorScheme="gray"
                        fontSize="xs"
                        px={2}
                        py={1}
                        cursor="pointer"
                        onClick={() => {
                          setFilterActive("");
                          bumpTablePage();
                        }}
                        _hover={{ opacity: 0.8 }}
                      >
                        Active: {filterActive === "true" ? "Active" : "Inactive"} ×
                      </Badge>
                    ) : null}
                    {filterGlobal ? (
                      <Badge
                        colorScheme="gray"
                        fontSize="xs"
                        px={2}
                        py={1}
                        cursor="pointer"
                        onClick={() => {
                          setFilterGlobal("");
                          bumpTablePage();
                        }}
                        _hover={{ opacity: 0.8 }}
                      >
                        Scope: {filterGlobal === "true" ? "Global" : "Tenant-scoped"} ×
                      </Badge>
                    ) : null}
                  </HStack>
                ) : null}
              </VStack>
            }
            hasActiveFilters={hasActiveFilters}
            onClearFilters={clearAllFilters}
            filterToolbarAlign="flex-end"
            filterToolbarRightContent={
              <Button size="sm" colorScheme="orange" leftIcon={<AddIcon />} onClick={openCreate}>
                Create policy
              </Button>
            }
            isLoading={loading}
            loadingMessage="Loading policies…"
            emptyMessage='No policies yet. Click "Create policy" to add one.'
            noResultsMessage="No policies match the current filters."
            unfilteredCount={allPolicies.length}
            onRowClick={(row) => openPolicyView(row.policy_id)}
            paginate="client"
            tableContainerProps={{ overflowX: "auto" }}
          />
        </CardBody>
      </Card>
    </Box>
  );
}
