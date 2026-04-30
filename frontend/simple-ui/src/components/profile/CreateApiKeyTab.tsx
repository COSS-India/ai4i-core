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
  InputGroup,
  InputRightElement,
  IconButton,
  HStack,
  Text,
  VStack,
  useColorModeValue,
  Button,
  Alert,
  AlertIcon,
  AlertDescription,
  Checkbox,
  CheckboxGroup,
  SimpleGrid,
  Badge,
  Wrap,
  WrapItem,
  Center,
  Spinner,
} from "@chakra-ui/react";
import { CopyIcon, CloseIcon } from "@chakra-ui/icons";
import { useCreateApiKeyTab } from "./hooks/useCreateApiKeyTab";
import { useToastWithDeduplication } from "../../hooks/useToastWithDeduplication";
import UserSearchableSelect from "../common/UserSearchableSelect";
import StandardModal from "../common/StandardModal";

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
          <HStack justify="space-between" align="flex-start">
            <Text fontSize="sm" color="gray.600">
              Assign permissions to users
            </Text>
            <Button
              size="sm"
              colorScheme="purple"
              onClick={perm.openManagePermissions}
              isDisabled={!perm.selectedUserForPermissions}
            >
              Manage Permissions
            </Button>
          </HStack>

          <Box>
          
            <FormControl>
              <FormLabel fontWeight="semibold">User</FormLabel>
              <UserSearchableSelect
                variant="pick"
                value={perm.selectedUserForPermissions?.id ?? null}
                onChange={(id, picked) => perm.handleUserSelect(id, picked)}
                seedUsers={users}
                isLoading={isLoadingUsers}
                isDisabled={isLoadingUsers}
                placeholder={isLoadingUsers ? "Loading users..." : "Select a user"}
                selectedPreview={perm.selectedUserForPermissions}
                allowClear
              />
            </FormControl>
          </Box>

          {perm.selectedUserForPermissions && (
            <Box>
              <Heading size="sm" mb={4} color="gray.700" userSelect="none" cursor="default">
                Current Permissions for {perm.selectedUserForPermissions.username}
              </Heading>
              {perm.selectedUserPermissions.length > 0 ? (
                <Wrap spacing={2}>
                  {perm.selectedUserPermissions.map((p) => (
                    <WrapItem key={p}>
                      <Badge colorScheme="purple" fontSize="sm" px={2} py={1}>
                        {p}
                      </Badge>
                    </WrapItem>
                  ))}
                </Wrap>
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

          {perm.createdApiKeyToken && (
            <Alert status="warning" borderRadius="md" variant="left-accent">
              <AlertIcon />
              <Box flex="1">
                <Text fontWeight="bold" mb={2}>
                  API Key Created — Copy it now!
                </Text>
                <Text fontSize="xs" color="gray.600" mb={2}>
                  This token will not be shown again. Store it securely.
                </Text>
                <InputGroup size="sm">
                  <Input
                    value={perm.createdApiKeyToken}
                    isReadOnly
                    fontFamily="mono"
                    fontSize="xs"
                    pr="4rem"
                  />
                  <InputRightElement width="4rem">
                    <HStack spacing={0}>
                      <IconButton
                        aria-label="Copy API key"
                        icon={<CopyIcon />}
                        size="xs"
                        onClick={() => {
                          navigator.clipboard.writeText(perm.createdApiKeyToken!);
                          toast({
                            title: "Copied",
                            description: "API key copied to clipboard",
                            status: "success",
                            duration: 2000,
                            isClosable: true,
                          });
                        }}
                      />
                      <IconButton
                        aria-label="Dismiss"
                        icon={<CloseIcon />}
                        size="xs"
                        variant="ghost"
                        onClick={perm.clearCreatedApiKeyToken}
                      />
                    </HStack>
                  </InputRightElement>
                </InputGroup>
              </Box>
            </Alert>
          )}

          <Alert status="info" borderRadius="md">
            <AlertIcon />
            <AlertDescription>
              Select a user, then click &quot;Manage Permissions&quot; to create an API key with scoped permissions.
            </AlertDescription>
          </Alert>
        </VStack>
      </CardBody>

      <StandardModal
        isOpen={perm.isManagePermissionsOpen}
        onClose={perm.closeManagePermissions}
        size="lg"
        title={`Create API Key ${perm.selectedUserForPermissions ? `for ${perm.selectedUserForPermissions.username}` : ""}`}
        footer={
          <>
            <Button variant="ghost" onClick={perm.closeManagePermissions} isDisabled={perm.isCreatingApiKeyForUser}>
              Cancel
            </Button>
            <Button
              ml={3}
              colorScheme="purple"
              onClick={perm.handleCreateApiKeyForUser}
              isLoading={perm.isCreatingApiKeyForUser}
              loadingText="Creating..."
            >
              Create API Key
            </Button>
          </>
        }
      >
        {perm.isLoadingPermissions ? (
          <Center py={6}>
            <Spinner size="md" color="purple.500" />
          </Center>
        ) : (
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
                    Select permissions for this API key
                  </Text>
                  <Box borderWidth="1px" borderRadius="md" p={4} bg="white" maxH="300px" overflowY="auto">
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
                                perm.setSelectedPermissionsForUser(perm.permissions.map((p) => p.name));
                              } else {
                                perm.setSelectedPermissionsForUser([]);
                              }
                            }}
                            colorScheme="purple"
                          >
                            <Text fontSize="sm" fontWeight="semibold">Select All</Text>
                          </Checkbox>
                          <Text fontSize="xs" color="gray.500">
                            {perm.selectedPermissionsForUser.length}/{perm.permissions.length} selected
                          </Text>
                        </HStack>
                      </Box>
                      <SimpleGrid columns={2} spacing={3}>
                        {perm.permissions.map((p) => (
                          <Checkbox key={p.name} value={p.name} colorScheme="purple">
                            <Text fontSize="sm">{p.name}</Text>
                          </Checkbox>
                        ))}
                      </SimpleGrid>
                    </CheckboxGroup>
                  </Box>
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
                      perm.setApiKeyForUser({ ...perm.apiKeyForUser, expires_days: next });
                    }}
                    min={1}
                    max={365}
                    bg="white"
                  />
                  <Text fontSize="xs" color="gray.500" mt={1}>
                    API key will expire after{" "}
                    {perm.apiKeyForUser.expires_days === "" ? "—" : `${perm.apiKeyForUser.expires_days} day(s)`}
                  </Text>
                </FormControl>
          </VStack>
        )}
      </StandardModal>
    </Card>
  );
}
