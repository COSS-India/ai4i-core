// PiiAuditTab

import {
  Button,
  Card,
  Box,
  CardBody,
  Heading,
  HStack,
  SimpleGrid,
  Text,
  VStack,
} from "@chakra-ui/react";
import AdminDataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  TableSearchField,
  TableSelectField,
} from "../common/AdminDataTable";
import type { UsePiiManagementReturn } from "./hooks/usePiiManagement";


type Props = UsePiiManagementReturn;

export default function PiiAuditTab(p: Props) {
  const {
    cardBg, borderColor, mutedText,
    allDomains, tenantMappings, activeDomainCount,
    auditLogs, auditLoading, sortedAuditLogs, auditColumns,
    auditSearch, setAuditSearch, auditDomainFilter, setAuditDomainFilter,
    auditTenantFilter, setAuditTenantFilter, auditSortDirection,
    auditHasActiveFilters, auditDomainOptions, auditTenantOptions,
    fetchAuditLogs, openAuditTraceDetail,
  } = p;

  return (            <VStack align="stretch" spacing={6}>
              <Card bg={cardBg} borderWidth="1px" borderColor={borderColor}>
                <CardBody>
                  <HStack justify="space-between" flexWrap="wrap" gap={3}>
                    <Box>
                      <Heading size="sm" mb={2}>
                        Audit Logs
                      </Heading>
                      <Text fontSize="sm" color={mutedText}>
                        Recent redact events captured by pii-service.
                      </Text>
                    </Box>
                    <Button size="sm" variant="outline" onClick={() => void fetchAuditLogs()}>
                      Refresh
                    </Button>
                  </HStack>
                </CardBody>
              </Card>
              <SimpleGrid columns={{ base: 1, md: 3 }} spacing={6}>
                <Card bg={cardBg} borderWidth="1px" borderColor={borderColor}>
                  <CardBody>
                    <Text fontSize="xs" color={mutedText} textTransform="uppercase" mb={2}>
                      Total Domains
                    </Text>
                    <Text fontSize="2xl" fontWeight="bold">
                      {allDomains.length}
                    </Text>
                  </CardBody>
                </Card>
                <Card bg={cardBg} borderWidth="1px" borderColor={borderColor}>
                  <CardBody>
                    <Text fontSize="xs" color={mutedText} textTransform="uppercase" mb={2}>
                      Active Domains
                    </Text>
                    <Text fontSize="2xl" fontWeight="bold">
                      {activeDomainCount}
                    </Text>
                  </CardBody>
                </Card>
                <Card bg={cardBg} borderWidth="1px" borderColor={borderColor}>
                  <CardBody>
                    <Text fontSize="xs" color={mutedText} textTransform="uppercase" mb={2}>
                      Tenant Mappings
                    </Text>
                    <Text fontSize="2xl" fontWeight="bold">
                      {tenantMappings.length}
                    </Text>
                  </CardBody>
                </Card>
              </SimpleGrid>
              <Card bg={cardBg} borderWidth="1px" borderColor={borderColor}>
                <CardBody>
                  <AdminDataTable
                    key={`audit-${auditSortDirection}`}
                    items={sortedAuditLogs}
                    columns={auditColumns}
                    getRowKey={(row) => String(row.id)}
                    paginate="client"
                    initialPageSize={10}
                    pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
                    isLoading={auditLoading}
                    loadingMessage="Loading logs…"
                    emptyMessage="No audit logs found."
                    noResultsMessage="No audit logs match the current filters."
                    unfilteredCount={auditLogs.length}
                    onRowClick={openAuditTraceDetail}
                    maxHeight="60vh"
                    tableContainerProps={{ overflowX: "auto" }}
                    filterToolbarRightContent={
                      <Button size="sm" variant="outline" onClick={() => void fetchAuditLogs()}>
                        Refresh
                      </Button>
                    }
                    filters={
                      <>
                        <TableSearchField
                          label="Search"
                          value={auditSearch}
                          onChange={setAuditSearch}
                          placeholder="Search trace / tenant / domain / target…"
                          formControlProps={{ w: { base: "full", md: "360px" } }}
                        />
                        <TableSelectField
                          label="Domain"
                          value={auditDomainFilter}
                          onChange={setAuditDomainFilter}
                        >
                          <option value="all">All domains</option>
                          {auditDomainOptions.map((id) => (
                            <option key={id} value={id}>
                              {id}
                            </option>
                          ))}
                        </TableSelectField>
                        <TableSelectField
                          label="Tenant"
                          value={auditTenantFilter}
                          onChange={setAuditTenantFilter}
                        >
                          <option value="all">All tenants</option>
                          {auditTenantOptions.map((id) => (
                            <option key={id} value={id}>
                              {id}
                            </option>
                          ))}
                        </TableSelectField>
                      </>
                    }
                    hasActiveFilters={auditHasActiveFilters}
                    onClearFilters={() => {
                      setAuditSearch("");
                      setAuditDomainFilter("all");
                      setAuditTenantFilter("all");
                    }}
                  />
                </CardBody>
              </Card>
            </VStack>
  );
}
