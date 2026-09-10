import {
  Badge,
  Box,
  Button,
  Center,
  Checkbox,
  Flex,
  Select,
  Spinner,
  Table,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
  VStack,
} from "@chakra-ui/react";
import React from "react";
import { useToastWithDeduplication } from "../../utils/toast";
import { useNotificationCatalog } from "../../hooks/useNotificationCatalog";
import { STANDARD_ALERT_THRESHOLDS } from "../../types/notificationAlerts";
import CatalogToolbar, { RecipientRoleCheckboxes } from "./CatalogToolbar";

const AlertsCatalogTab: React.FC = () => {
  const toast = useToastWithDeduplication();
  const {
    filteredItems,
    search,
    setSearch,
    statusFilter,
    setStatusFilter,
    isLoading,
    isSubmitting,
    error,
    getDraft,
    setEnabled,
    setAllEnabled,
    setRecipientRole,
    setThreshold,
    allFilteredEnabled,
    dirtyCount,
    submit,
  } = useNotificationCatalog("ALERT");

  const handleSubmit = async () => {
    try {
      const changed = await submit();
      toast({
        title: changed
          ? `${changed} alert${changed > 1 ? "s" : ""} updated`
          : "No changes to save",
        status: changed ? "success" : "info",
        duration: 3000,
        isClosable: true,
      });
    } catch {
      toast({
        title: "Failed to save alerts",
        description: error ?? "Please try again.",
        status: "error",
        duration: 4000,
        isClosable: true,
      });
    }
  };

  if (isLoading) {
    return (
      <Center py={16}>
        <Spinner size="lg" color="blue.500" />
      </Center>
    );
  }

  return (
    <Box>
      <CatalogToolbar
        search={search}
        onSearchChange={setSearch}
        statusFilter={statusFilter}
        onStatusFilterChange={setStatusFilter}
        hint="Set the Recipient Role and Threshold values for any alert. Check the ones you want Enabled, uncheck the ones you want Disabled, then Submit."
      />

      {error ? (
        <Text color="red.500" fontSize="sm" mb={3}>
          {error}
        </Text>
      ) : null}

      <Box overflowX="auto" borderWidth="1px" borderColor="gray.200" borderRadius="md">
        <Table size="md" variant="simple">
          <Thead bg="gray.50">
            <Tr>
              <Th w="48px">
                <Checkbox
                  isChecked={allFilteredEnabled}
                  isIndeterminate={
                    !allFilteredEnabled &&
                    filteredItems.some((item) => getDraft(item).enabled)
                  }
                  onChange={(e) => setAllEnabled(e.target.checked)}
                  aria-label="Enable or disable all visible alerts"
                />
              </Th>
              <Th>Alert Name</Th>
              <Th>Recipient Role</Th>
              <Th>Delivery Channel</Th>
              <Th>Thresholds</Th>
            </Tr>
          </Thead>
          <Tbody>
            {filteredItems.length === 0 ? (
              <Tr>
                <Td colSpan={5}>
                  <Text color="gray.500" textAlign="center" py={8}>
                    No alerts match your filters.
                  </Text>
                </Td>
              </Tr>
            ) : (
              filteredItems.map((item) => {
                const draft = getDraft(item);
                return (
                  <Tr key={item.name}>
                    <Td verticalAlign="top" pt={4}>
                      <Checkbox
                        isChecked={draft.enabled}
                        onChange={(e) => setEnabled(item.name, e.target.checked)}
                        aria-label={`Enable ${item.display_name}`}
                      />
                    </Td>
                    <Td verticalAlign="top">
                      <VStack align="start" spacing={1}>
                        <Flex align="center" gap={2} flexWrap="wrap">
                          <Text fontWeight="semibold">{item.display_name}</Text>
                          {item.origin === "seeded" ? (
                            <Badge colorScheme="gray" fontWeight="normal">
                              System-seeded
                            </Badge>
                          ) : null}
                        </Flex>
                        <Text fontSize="sm" color="gray.600" noOfLines={2}>
                          {item.description}
                        </Text>
                      </VStack>
                    </Td>
                    <Td verticalAlign="top" pt={3}>
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
                    </Td>
                    <Td verticalAlign="top" pt={3}>
                      <Select
                        value={item.channels[0] ?? "EMAIL"}
                        isDisabled
                        maxW="140px"
                        size="sm"
                        bg="gray.50"
                      >
                        <option value="EMAIL">Email</option>
                      </Select>
                    </Td>
                    <Td verticalAlign="top" pt={3}>
                      <VStack align="start" spacing={1}>
                        {STANDARD_ALERT_THRESHOLDS.map((threshold) => (
                          <Checkbox
                            key={threshold}
                            isChecked={Boolean(draft.thresholds?.[threshold])}
                            onChange={(e) =>
                              setThreshold(item.name, threshold, e.target.checked)
                            }
                          >
                            <Text fontSize="sm">{threshold}%</Text>
                          </Checkbox>
                        ))}
                      </VStack>
                    </Td>
                  </Tr>
                );
              })
            )}
          </Tbody>
        </Table>
      </Box>

      <Flex justify="flex-end" mt={4}>
        <Button
          colorScheme="blue"
          onClick={() => void handleSubmit()}
          isLoading={isSubmitting}
          isDisabled={isSubmitting}
        >
          Submit{dirtyCount > 0 ? ` (${dirtyCount})` : ""}
        </Button>
      </Flex>
    </Box>
  );
};

export default AlertsCatalogTab;
