import {
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
  bandsForItem,
  type NotificationAlertType,
} from "../../types/notificationAlerts";
import { replaceTenantCopy } from "../../utils/replaceTenantCopy";
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
    isLoading,
    isSubmitting,
    error,
    getDraft,
    setRecipientRole,
    setThreshold,
    dirtyCount,
    submit,
  } = useNotificationCatalog(type);

  const colSpan = showThresholds ? 4 : 3;

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
            ? replaceTenantCopy(
                `Saved: ${result.succeeded.join(", ")}. Failed on '${result.failed.name}': ${result.failed.message}`,
              )
            : replaceTenantCopy(result.failed.message),
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
        hint={hint}
      />

      {error ? (
        <Text color="red.500" fontSize="sm" mb={3}>
          {replaceTenantCopy(error)}
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
                return (
                  <Tr key={item.name}>
                    <Td verticalAlign="top">
                      <VStack align="start" spacing={1}>
                        <Flex align="center" gap={2} flexWrap="wrap">
                          <Text fontWeight="semibold">
                            {replaceTenantCopy(item.display_name)}
                          </Text>
                        </Flex>
                        <Text fontSize="sm" color="gray.600" noOfLines={2}>
                          {replaceTenantCopy(item.description)}
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
                          {bandsForItem(draft.thresholds).map((band) => (
                            <Checkbox
                              key={band.percentage}
                              isChecked={band.active}
                              onChange={(e) =>
                                setThreshold(
                                  item.name,
                                  band.percentage,
                                  e.target.checked,
                                )
                              }
                            >
                              <Text fontSize="sm">{band.percentage}%</Text>
                            </Checkbox>
                          ))}
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
