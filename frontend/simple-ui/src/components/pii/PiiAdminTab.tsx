// PiiAdminTab

import {
  Alert,
  AlertDescription,
  AlertIcon,
  Badge,
  Box,
  Button,
  Card,
  CardBody,
  Checkbox,
  FormControl,
  FormLabel,
  GridItem,
  HStack,
  IconButton,
  Input,
  Select,
  SimpleGrid,
  Text,
  Tooltip,
  VStack,
} from "@chakra-ui/react";
import { EditIcon } from "@chakra-ui/icons";
import AdminDataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  TableSearchField,
  TableSelectField,
} from "../common/AdminDataTable";
import type { UsePiiManagementReturn } from "./hooks/usePiiManagement";
import type { Domain, Rule, TenantDomainMappingRow } from "./types";


type Props = UsePiiManagementReturn;

export default function PiiAdminTab(p: Props) {
  const {
    cardBg, borderColor, tableRowHoverBg, mutedText, readOnlyInputBg,
    allDomains, checkedDomains, newDomainId, setNewDomainId, editingDomainId, editingRules,
    tenantMappings, newMapTenantId, setNewMapTenantId, newMapDomainId, setNewMapDomainId,
    newEntity, setNewEntity, newAction, setNewAction, newExample, setNewExample, newRegex, setNewRegex,
    adminDataError, rulesSortDirection, mappingSearch, setMappingSearch, mappingDomainFilter, setMappingDomainFilter,
    mappingSortDirection, sortedRules, sortedMappings, mappingHasActiveFilters, rulesColumns, mappingColumns,
    handleToggleDomainActivate, applyActiveDomains, handleCreateDomain, loadDomainConfig,
    generateRegex, addCustomRule, saveConfig, refreshAdminDataWithRetry, handleSaveTenantMapping,
    openDomainDetail, openRuleDetail, openMappingDetail,
  } = p;

  return (            <SimpleGrid columns={{ base: 1, md: 3 }} spacing={6}>
              <Card bg={cardBg} borderWidth="1px" borderColor={borderColor} h={{ base: "auto", md: "600px" }}>
                <CardBody display="flex" flexDirection="column" h="full">
                  <Text fontSize="xs" fontWeight="bold" color={mutedText} textTransform="uppercase" letterSpacing="wider" borderBottomWidth="1px" borderColor={borderColor} pb={2} mb={4}>
                    Domain Inventory
                  </Text>
                  <VStack align="stretch" spacing={2} flex="1" overflowY="auto" mb={4}>
                    {allDomains.map((d: Domain) => (
                      <HStack
                        key={d.domain_id}
                        justify="space-between"
                        p={2}
                        borderWidth="1px"
                        borderRadius="md"
                        borderColor={borderColor}
                        _hover={{ bg: tableRowHoverBg }}
                        cursor="pointer"
                        onClick={() => openDomainDetail(d)}
                      >
                        <HStack spacing={3} flex="1" minW={0}>
                          <Box onClick={(e) => e.stopPropagation()}>
                            <Checkbox
                              isChecked={checkedDomains.has(d.domain_id)}
                              onChange={() => handleToggleDomainActivate(d.domain_id)}
                            />
                          </Box>
                          <Text fontWeight="semibold" fontSize="sm" noOfLines={1}>
                            {d.domain_id.toUpperCase()}
                          </Text>
                        </HStack>
                        <Box onClick={(e) => e.stopPropagation()}>
                          <Tooltip label="Edit policy rules" hasArrow placement="top">
                            <IconButton
                              aria-label="Edit policy rules for domain"
                              icon={<EditIcon />}
                              size="sm"
                              variant="ghost"
                              colorScheme="blue"
                              _hover={{ bg: "blue.50" }}
                              onClick={() => void loadDomainConfig(d.domain_id)}
                            />
                          </Tooltip>
                        </Box>
                      </HStack>
                    ))}
                  </VStack>
                  <Button
                    colorScheme="gray"
                    isDisabled={checkedDomains.size === 0}
                    onClick={() => void applyActiveDomains()}
                    mb={4}
                  >
                    Apply Active Domains ({checkedDomains.size})
                  </Button>
                  <Box borderTopWidth="1px" borderColor={borderColor} pt={4}>
                    <Input
                      size="sm"
                      placeholder="New domain id"
                      mb={2}
                      bg={cardBg}
                      value={newDomainId}
                      onChange={(e) => setNewDomainId(e.target.value)}
                    />
                    <Button size="sm" variant="outline" w="full" onClick={() => void handleCreateDomain()}>
                      Create Domain
                    </Button>
                  </Box>
                </CardBody>
              </Card>

              <GridItem colSpan={{ base: 1, md: 2 }}>
                <Card bg={cardBg} borderWidth="1px" borderColor={borderColor} h={{ base: "auto", md: "600px" }}>
                  <CardBody display="flex" flexDirection="column" h="full">
                    <HStack justify="space-between" borderBottomWidth="1px" borderColor={borderColor} pb={2} mb={4} flexWrap="wrap">
                      <Text fontSize="xs" fontWeight="bold" color={mutedText} textTransform="uppercase" letterSpacing="wider">
                        Policy Rules
                      </Text>
                      {editingDomainId ? (
                        <Badge colorScheme="yellow">Editing: {editingDomainId}</Badge>
                      ) : null}
                    </HStack>

                    <Box flex="1" mb={4}>
                      <AdminDataTable
                        key={`rules-${editingDomainId ?? "none"}-${rulesSortDirection}`}
                        items={sortedRules}
                        columns={rulesColumns}
                        getRowKey={(r) => `${r.entity_type}-${r.action}-${r.custom_regex ?? ""}`}
                        paginate="client"
                        initialPageSize={10}
                        pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
                        emptyMessage="No rules configured for this domain."
                        onRowClick={openRuleDetail}
                        maxHeight="280px"
                        tableContainerProps={{
                          borderWidth: "1px",
                          borderRadius: "md",
                          borderColor,
                        }}
                      />
                    </Box>

                    <Box borderWidth="1px" borderRadius="md" borderColor={borderColor} p={4} mb={4} bg={cardBg}>
                      <Text fontSize="sm" fontWeight="bold" color="blue.500" mb={3}>
                        Add Custom Rule
                      </Text>
                      <SimpleGrid columns={{ base: 1, md: 12 }} spacing={2} mb={2}>
                        <GridItem colSpan={{ base: 1, md: 3 }}>
                          <Input
                            size="sm"
                            placeholder="Entity (e.g., PASSPORT)"
                            value={newEntity}
                            onChange={(e) => setNewEntity(e.target.value)}
                            bg={cardBg}
                          />
                        </GridItem>
                        <GridItem colSpan={{ base: 1, md: 3 }}>
                          <Select size="sm" value={newAction} onChange={(e) => setNewAction(e.target.value)} bg={cardBg} placeholder="Select action">
                            <option value="REDACT_TAG">REDACT_TAG</option>
                            <option value="MASK">MASK</option>
                            <option value="HASH">HASH</option>
                          </Select>
                        </GridItem>
                        <GridItem colSpan={{ base: 1, md: 6 }}>
                          <HStack
                            spacing={3}
                            align="stretch"
                            flexWrap={{ base: "wrap", md: "nowrap" }}
                          >
                            <Input
                              size="sm"
                              flex="1"
                              minW={{ base: "100%", md: "140px" }}
                              placeholder="AI Example (e.g., A1234567)"
                              value={newExample}
                              onChange={(e) => setNewExample(e.target.value)}
                              bg={cardBg}
                            />
                            <Button
                              size="sm"
                              colorScheme="orange"
                              flexShrink={0}
                              whiteSpace="nowrap"
                              px={4}
                              onClick={() => void generateRegex()}
                            >
                              Generate Regex
                            </Button>
                          </HStack>
                        </GridItem>
                      </SimpleGrid>
                      <Input
                        size="sm"
                        placeholder="Generated Regex / Pattern"
                        readOnly
                        fontFamily="mono"
                        mb={2}
                        bg={readOnlyInputBg}
                        value={newRegex}
                      />
                      <Button size="sm" variant="outline" colorScheme="blue" w="full" onClick={addCustomRule}>
                        Add Rule
                      </Button>
                    </Box>

                    <Button colorScheme="green" onClick={() => void saveConfig()}>
                      Save Policy
                    </Button>
                  </CardBody>
                </Card>
              </GridItem>

              <GridItem colSpan={{ base: 1, md: 3 }}>
                <Card bg={cardBg} borderWidth="1px" borderColor={borderColor}>
                  <CardBody>
                    <Text fontSize="xs" fontWeight="bold" color={mutedText} textTransform="uppercase" letterSpacing="wider" borderBottomWidth="1px" borderColor={borderColor} pb={2} mb={4}>
                      Tenant to Domain Mapping
                    </Text>
                    <SimpleGrid columns={{ base: 1, md: 2 }} spacing={3} mb={4}>
                      <FormControl>
                        <FormLabel fontSize="xs">Tenant ID</FormLabel>
                        <Input
                          size="sm"
                          placeholder="tenant uuid/slug"
                          value={newMapTenantId}
                          onChange={(e) => setNewMapTenantId(e.target.value)}
                          bg={cardBg}
                        />
                      </FormControl>
                      <FormControl>
                        <FormLabel fontSize="xs">Domain</FormLabel>
                        <Select
                          size="sm"
                          placeholder="Select domain"
                          value={newMapDomainId}
                          onChange={(e) => setNewMapDomainId(e.target.value)}
                          bg={cardBg}
                        >
                          <option value="">Select domain</option>
                          {allDomains.map((d: Domain) => (
                            <option key={d.domain_id} value={d.domain_id}>
                              {d.domain_id}
                              {d.is_active ? " (active)" : ""}
                            </option>
                          ))}
                        </Select>
                      </FormControl>
                    </SimpleGrid>
                    <HStack spacing={2} mb={4} flexWrap="wrap">
                      <Button size="sm" colorScheme="blue" onClick={() => void handleSaveTenantMapping()}>
                        Save
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => void refreshAdminDataWithRetry()}>
                        Refresh
                      </Button>
                    </HStack>
                    {adminDataError ? (
                      <Alert status="error" size="sm" borderRadius="md" mb={4}>
                        <AlertIcon />
                        <AlertDescription fontSize="xs">{adminDataError}</AlertDescription>
                      </Alert>
                    ) : null}
                    <AdminDataTable
                      key={`mappings-${mappingSortDirection}`}
                      items={sortedMappings}
                      columns={mappingColumns}
                      getRowKey={(row) => row.tenant_id}
                      paginate="client"
                      initialPageSize={10}
                      pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
                      emptyMessage="No mappings configured."
                      noResultsMessage="No mappings match the current filters."
                      unfilteredCount={tenantMappings.length}
                      onRowClick={openMappingDetail}
                      maxHeight="50vh"
                      filters={
                        <>
                          <TableSearchField
                            label="Search"
                            value={mappingSearch}
                            onChange={setMappingSearch}
                            placeholder="Search tenant or domain…"
                          />
                          <TableSelectField
                            label="Domain"
                            value={mappingDomainFilter}
                            onChange={setMappingDomainFilter}
                          >
                            <option value="all">All domains</option>
                            {allDomains.map((d: Domain) => (
                              <option key={d.domain_id} value={d.domain_id}>
                                {d.domain_id}
                              </option>
                            ))}
                          </TableSelectField>
                        </>
                      }
                      hasActiveFilters={mappingHasActiveFilters}
                      onClearFilters={() => {
                        setMappingSearch("");
                        setMappingDomainFilter("all");
                      }}
                    />
                  </CardBody>
                </Card>
              </GridItem>
            </SimpleGrid>
  );
}
