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
import {
  thresholdKeysForItem,
  type NotificationAlertType,
} from "../../types/notificationAlerts";
import CatalogToolbar, { RecipientRoleCheckboxes } from "./CatalogToolbar";

interface CatalogTabProps {
  type: NotificationAlertType;
  hint: string;
  nameColumnHeader: string;
  emptyMessage: string;
  entityLabel: string;
  showThresholds?: boolean;
}

const CatalogTab: React.FC<CatalogTabProps> = ({
  type,
  hint,
  nameColumnHeader,
  emptyMessage,
  entityLabel,
  showThresholds = false,
}) => {
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
    draftEnabled,
    setEnabled,
    setAllEnabled,
    setRecipientRole,
    setThreshold,
    allFilteredEnabled,
    dirtyCount,
    submit,
  } = useNotificationCatalog(type);

  const colSpan = showThresholds ? 5 : 4;

  const handleSubmit = async () => {
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
        hint={hint}
      />

      {error ? (
        <Text color="red.500" fontSize="sm" mb={3}>
          {error}
        </Text>
      ) : null}

      <Box
        overflowX="auto"
        borderWidth="1px"
        borderColor="gray.200"
        borderRadius="md"
      >
        <Table size="md" variant="simple">
          <Thead bg="gray.50">
            <Tr>
              <Th w="48px">
                <Checkbox
                  isChecked={allFilteredEnabled}
                  isIndeterminate={
                    !allFilteredEnabled &&
                    filteredItems.some((item) => draftEnabled(getDraft(item)))
                  }
                  onChange={(e) => setAllEnabled(e.target.checked)}
                  aria-label={`Enable or disable all visible ${entityLabel}s`}
                />
              </Th>
              <Th>{nameColumnHeader}</Th>
              <Th>Recipient Role</Th>
              <Th>Delivery Channel</Th>
              {showThresholds ? <Th>Thresholds</Th> : null}
            </Tr>
          </Thead>
          <Tbody>
            {filteredItems.length === 0 ? (
              <Tr>
                <Td colSpan={colSpan}>
                  <Text color="gray.500" textAlign="center" py={8}>
                    {emptyMessage}
                  </Text>
                </Td>
              </Tr>
            ) : (
              filteredItems.map((item) => {
                const draft = getDraft(item);
                const enabled = draftEnabled(draft);
                return (
                  <Tr key={item.name}>
                    <Td verticalAlign="top" pt={4}>
                      <Checkbox
                        isChecked={enabled}
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
                    {showThresholds ? (
                      <Td verticalAlign="top" pt={3}>
                        <VStack align="start" spacing={1}>
                          {thresholdKeysForItem(draft.thresholds).map(
                            (threshold) => (
                              <Checkbox
                                key={threshold}
                                isChecked={Boolean(
                                  draft.thresholds?.[threshold],
                                )}
                                onChange={(e) =>
                                  setThreshold(
                                    item.name,
                                    threshold,
                                    e.target.checked,
                                  )
                                }
                              >
                                <Text fontSize="sm">{threshold}%</Text>
                              </Checkbox>
                            ),
                          )}
                        </VStack>
                      </Td>
                    ) : null}
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

export default CatalogTab;
