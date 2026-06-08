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
import type { PiiTypeOut } from "../../services/policyService";
import { MASK_OPTIONS } from "./constants";
import type { UsePiiTypesPanelReturn } from "./hooks/usePiiTypesPanel";

type Props = UsePiiTypesPanelReturn;

export default function PiiTypesTable(p: Props) {
  const {
    error,
    cardBg,
    borderColor,
    tableEpoch,
    filteredPiiTypes,
    piiColumns,
    searchQuery,
    setSearchQuery,
    filterMask,
    setFilterMask,
    hasActiveFilters,
    clearAllFilters,
    bumpTablePage,
    openCreate,
    loading,
    allTypes,
    openPiiView,
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
          <AdminDataTable<PiiTypeOut>
            key={tableEpoch}
            items={filteredPiiTypes}
            columns={piiColumns}
            getRowKey={(row) => row.pii_type_id}
            filters={
              <VStack align="stretch" spacing={3} flex="1" w="full">
                <HStack spacing={3} align="flex-end" flexWrap="wrap" rowGap={3} w="full">
                  <TableSearchField
                    label="Search"
                    value={searchQuery}
                    onChange={setSearchQuery}
                    placeholder="Search by label or regex…"
                    formControlProps={{ w: { base: "full", md: "280px" } }}
                    inputProps={{ pl: 10 }}
                  />
                  <TableSelectField
                    label="Mask format"
                    value={filterMask}
                    onChange={setFilterMask}
                    formControlProps={{ w: { base: "full", sm: "160px" } }}
                  >
                    <option value="">All</option>
                    {MASK_OPTIONS.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
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
                    {filterMask ? (
                      <Badge
                        colorScheme="gray"
                        fontSize="xs"
                        px={2}
                        py={1}
                        cursor="pointer"
                        onClick={() => {
                          setFilterMask("");
                          bumpTablePage();
                        }}
                        _hover={{ opacity: 0.8 }}
                      >
                        Mask: {filterMask} ×
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
                Create PII type
              </Button>
            }
            isLoading={loading}
            loadingMessage="Loading PII types…"
            emptyMessage='No PII types in the library yet. Click "Create PII type" to add one.'
            noResultsMessage="No PII types match the current filters."
            unfilteredCount={allTypes.length}
            onRowClick={openPiiView}
            paginate="client"
            tableContainerProps={{ overflowX: "auto" }}
          />
        </CardBody>
      </Card>
    </Box>
  );
}
