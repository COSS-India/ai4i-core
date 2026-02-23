import React from "react";
import {
  Box,
  Card,
  CardBody,
  CardHeader,
  FormControl,
  FormLabel,
  Heading,
  Input,
  HStack,
  Text,
  VStack,
  useColorModeValue,
  Button,
  Select,
  Alert,
  AlertIcon,
  AlertDescription,
  Checkbox,
  CheckboxGroup,
  SimpleGrid,
  Badge,
} from "@chakra-ui/react";
import { useCreateApiKeyTab } from "./hooks/useCreateApiKeyTab";
import { useToastWithDeduplication } from "../../hooks/useToastWithDeduplication";

export interface CreateApiKeyTabProps {
  users: import("../../types/auth").User[];
  isLoadingUsers: boolean;
  setApiKeys: (keys: import("../../types/auth").APIKeyResponse[]) => void;
  setSelectedApiKeyId: (id: number | null) => void;
}

export default function CreateApiKeyTab({
  users,
  isLoadingUsers,
  setApiKeys,
  setSelectedApiKeyId,
}: CreateApiKeyTabProps) {
  const toast = useToastWithDeduplication();
  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");
  const inputReadOnlyBg = useColorModeValue("gray.50", "gray.700");

  const perm = useCreateApiKeyTab({
    users,
    isLoadingUsers,
    setApiKeys,
    setSelectedApiKeyId,
  });

  return (
    <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
      <CardHeader>
        <Heading size="md" color="gray.700" userSelect="none" cursor="default">
          Permissions Management
        </Heading>
      </CardHeader>
      <CardBody>
        <VStack spacing={6} align="stretch">
          <HStack justify="space-between">
            <Text fontSize="sm" color="gray.600">
              Assign permissions to users
            </Text>
            <Button
              size="sm"
              colorScheme="purple"
              onClick={perm.handleLoadPermissions}
              isLoading={perm.isLoadingPermissions}
              loadingText="Loading..."
            >
              Load Permissions
            </Button>
          </HStack>

          <Box>
            <Heading size="sm" mb={4} color="gray.700" userSelect="none" cursor="default">
              Select User
            </Heading>
            <FormControl>
              <FormLabel fontWeight="semibold">User</FormLabel>
              <Select
                value={perm.selectedUserForPermissions?.id ?? ""}
                onChange={(e) => {
                  const userId = parseInt(e.target.value, 10);
                  perm.handleUserSelect(userId);
                }}
                placeholder={isLoadingUsers ? "Loading users..." : "Select a user"}
                bg="white"
                isDisabled={isLoadingUsers}
              >
                {users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.username} ({u.email})
                  </option>
                ))}
              </Select>
            </FormControl>
          </Box>

          {perm.selectedUserForPermissions && (
            <Box>
              <Heading size="sm" mb={4} color="gray.700" userSelect="none" cursor="default">
                Current Permissions for {perm.selectedUserForPermissions.username}
              </Heading>
              {perm.selectedUserPermissions.length > 0 ? (
                <VStack spacing={2} align="stretch">
                  {perm.selectedUserPermissions.map((p) => (
                    <HStack
                      key={p}
                      justify="space-between"
                      p={3}
                      bg={inputReadOnlyBg}
                      borderRadius="md"
                    >
                      <Badge colorScheme="purple" fontSize="sm" p={1}>
                        {p}
                      </Badge>
                      <Button
                        size="xs"
                        colorScheme="red"
                        variant="outline"
                        onClick={() => {
                          toast({
                            title: "Info",
                            description: "Remove permission functionality will be implemented",
                            status: "info",
                            duration: 3000,
                            isClosable: true,
                          });
                        }}
                      >
                        Remove
                      </Button>
                    </HStack>
                  ))}
                </VStack>
              ) : (
                <Alert status="info" borderRadius="md">
                  <AlertIcon />
                  <AlertDescription>
                    This user has no direct permissions assigned (permissions come from roles).
                  </AlertDescription>
                </Alert>
              )}
            </Box>
          )}

          {perm.selectedUserForPermissions && perm.permissions.length > 0 && (
            <Box>
              <Heading size="sm" mb={4} color="gray.700" userSelect="none" cursor="default">
                Create API Key for {perm.selectedUserForPermissions.username}
              </Heading>
              <VStack spacing={4} align="stretch">
                <FormControl>
                  <FormLabel fontWeight="semibold">Key Name</FormLabel>
                  <Input
                    value={perm.apiKeyForUser.key_name}
                    onChange={(e) =>
                      perm.setApiKeyForUser({ ...perm.apiKeyForUser, key_name: e.target.value })
                    }
                    placeholder="Enter a name for this API key"
                    bg="white"
                  />
                </FormControl>

                <FormControl>
                  <FormLabel fontWeight="semibold">Permissions</FormLabel>
                  <Text fontSize="sm" color="gray.600" mb={3}>
                    Select permissions to find matching API key
                  </Text>
                  <Box
                    borderWidth="1px"
                    borderRadius="md"
                    p={4}
                    bg="white"
                    maxH="300px"
                    overflowY="auto"
                  >
                    <CheckboxGroup
                      value={perm.selectedPermissionsForUser}
                      onChange={(values) => perm.setSelectedPermissionsForUser(values as string[])}
                    >
                      <Box mb={3} pb={3} borderBottomWidth="1px">
                        <HStack justify="space-between" align="center">
                          <Checkbox
                            isChecked={
                              perm.selectedPermissionsForUser.length === perm.permissions.length &&
                              perm.permissions.length > 0
                            }
                            onChange={(e) => {
                              if (e.target.checked) {
                                perm.setSelectedPermissionsForUser([...perm.permissions]);
                              } else {
                                perm.setSelectedPermissionsForUser([]);
                              }
                            }}
                            colorScheme="purple"
                          >
                            <Text fontSize="sm" fontWeight="semibold">
                              Select All
                            </Text>
                          </Checkbox>
                          <Text fontSize="xs" color="gray.500">
                            {perm.selectedPermissionsForUser.length}/{perm.permissions.length}{" "}
                            selected
                          </Text>
                        </HStack>
                      </Box>
                      <SimpleGrid columns={2} spacing={3}>
                        {perm.permissions.map((p) => (
                          <Checkbox key={p} value={p} colorScheme="purple">
                            <Text fontSize="sm">{p}</Text>
                          </Checkbox>
                        ))}
                      </SimpleGrid>
                    </CheckboxGroup>
                  </Box>
                  {perm.selectedPermissionsForUser.length > 0 && (
                    <Box mt={3}>
                      <Text fontSize="sm" fontWeight="semibold" mb={2} color="gray.700">
                        Selected Permissions ({perm.selectedPermissionsForUser.length}):
                      </Text>
                      <HStack flexWrap="wrap" spacing={2}>
                        {perm.selectedPermissionsForUser.map((p) => (
                          <Badge key={p} colorScheme="purple" fontSize="sm" p={1}>
                            {p}
                          </Badge>
                        ))}
                      </HStack>
                    </Box>
                  )}
                </FormControl>

                <FormControl>
                  <FormLabel fontWeight="semibold">Expiry (Days)</FormLabel>
                  <Input
                    type="number"
                    value={perm.apiKeyForUser.expires_days === "" ? "" : perm.apiKeyForUser.expires_days}
                    onChange={(e) => {
                      const raw = e.target.value;
                      const next =
                        raw === ""
                          ? ""
                          : (() => {
                              const n = parseInt(raw, 10);
                              return Number.isNaN(n) ? "" : n;
                            })();
                      perm.setApiKeyForUser({
                        ...perm.apiKeyForUser,
                        expires_days: next,
                      });
                    }}
                    min={1}
                    max={365}
                    bg="white"
                  />
                  <Text fontSize="xs" color="gray.500" mt={1}>
                    API key will expire after{" "}
                    {perm.apiKeyForUser.expires_days === ""
                      ? 30
                      : perm.apiKeyForUser.expires_days}{" "}
                    day(s)
                  </Text>
                </FormControl>

                <Button
                  colorScheme="purple"
                  onClick={perm.handleCreateApiKeyForUser}
                  isLoading={perm.isCreatingApiKeyForUser}
                  loadingText="Creating..."
                >
                  Add Permission (Create API Key)
                </Button>
              </VStack>
            </Box>
          )}

          {perm.permissions.length === 0 && !perm.isLoadingPermissions && (
            <Alert status="info" borderRadius="md">
              <AlertIcon />
              <AlertDescription>
                Click &quot;Load Permissions&quot; to view all available permissions in the system.
              </AlertDescription>
            </Alert>
          )}

          <Alert status="info" borderRadius="md">
            <AlertIcon />
            <AlertDescription>
              Permissions are typically assigned through roles. Direct permission assignment may
              require backend support.
            </AlertDescription>
          </Alert>
        </VStack>
      </CardBody>
    </Card>
  );
}
