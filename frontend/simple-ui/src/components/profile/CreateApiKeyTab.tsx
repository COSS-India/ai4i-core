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
  Center,
  Spinner,
} from "@chakra-ui/react";
import { CopyIcon, CloseIcon } from "@chakra-ui/icons";
import { useCreateApiKeyTab } from "./hooks/useCreateApiKeyTab";
import { useToastWithDeduplication } from "../../utils/toast";

export interface CreateApiKeyTabProps {
  onApiKeyCreated?: () => void;
}

export default function CreateApiKeyTab({ onApiKeyCreated }: CreateApiKeyTabProps) {
  const toast = useToastWithDeduplication();
  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");

  const create = useCreateApiKeyTab({ onApiKeyCreated });

  return (
    <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
      <CardHeader>
        <Heading size="md" color="gray.700" userSelect="none" cursor="default">
          Create API Key
        </Heading>
      </CardHeader>
      <CardBody>
        {create.isLoadingPermissions ? (
          <Center py={8}>
            <Spinner size="lg" color="blue.500" />
          </Center>
        ) : (
          <VStack spacing={6} align="stretch">
            {create.createdApiKeyToken && (
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
                      value={create.createdApiKeyToken}
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
                            navigator.clipboard.writeText(create.createdApiKeyToken!);
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
                          onClick={create.clearCreatedApiKeyToken}
                        />
                      </HStack>
                    </InputRightElement>
                  </InputGroup>
                </Box>
              </Alert>
            )}

            <FormControl isRequired>
              <FormLabel fontWeight="semibold">Key Name</FormLabel>
              <Input
                value={create.apiKeyForm.key_name}
                onChange={(e) =>
                  create.setApiKeyForm({ ...create.apiKeyForm, key_name: e.target.value })
                }
                placeholder="Enter a name for this API key"
                bg="white"
              />
            </FormControl>

            <FormControl isRequired>
              <FormLabel fontWeight="semibold">Permissions</FormLabel>
              <Text fontSize="sm" color="gray.600" mb={3}>
                Select permissions for this API key
              </Text>
              <Box borderWidth="1px" borderRadius="md" p={4} bg="white" maxH="300px" overflowY="auto">
                <CheckboxGroup
                  value={create.selectedPermissions}
                  onChange={(values) => create.setSelectedPermissions(values as string[])}
                >
                  <Box mb={3} pb={3} borderBottomWidth="1px">
                    <HStack justify="space-between" align="center">
                      <Checkbox
                        isChecked={
                          create.selectedPermissions.length === create.permissions.length &&
                          create.permissions.length > 0
                        }
                        onChange={(e) => {
                          if (e.target.checked) {
                            create.setSelectedPermissions(create.permissions.map((p) => p.name));
                          } else {
                            create.setSelectedPermissions([]);
                          }
                        }}
                        colorScheme="blue"
                      >
                        <Text fontSize="sm" fontWeight="semibold">
                          Select All
                        </Text>
                      </Checkbox>
                      <Text fontSize="xs" color="gray.500">
                        {create.selectedPermissions.length}/{create.permissions.length} selected
                      </Text>
                    </HStack>
                  </Box>
                  <SimpleGrid columns={2} spacing={3}>
                    {create.permissions.map((p) => (
                      <Checkbox key={p.name} value={p.name} colorScheme="blue">
                        <Text fontSize="sm">{p.name}</Text>
                      </Checkbox>
                    ))}
                  </SimpleGrid>
                </CheckboxGroup>
              </Box>
            </FormControl>

            <FormControl isRequired>
              <FormLabel fontWeight="semibold">Expiry (Days)</FormLabel>
              <Input
                type="number"
                value={create.apiKeyForm.expires_days === "" ? "" : create.apiKeyForm.expires_days}
                onChange={(e) => {
                  const raw = e.target.value;
                  const next =
                    raw === ""
                      ? ""
                      : (() => {
                          const n = Number.parseInt(raw, 10);
                          return Number.isNaN(n) ? "" : n;
                        })();
                  create.setApiKeyForm({ ...create.apiKeyForm, expires_days: next });
                }}
                min={1}
                max={365}
                bg="white"
              />
              <Text fontSize="xs" color="gray.500" mt={1}>
                API key will expire after{" "}
                {create.apiKeyForm.expires_days === ""
                  ? "—"
                  : `${create.apiKeyForm.expires_days} day(s)`}
              </Text>
            </FormControl>

            <Button
              colorScheme="blue"
              alignSelf="flex-start"
              onClick={create.handleCreateApiKey}
              isLoading={create.isCreating}
              loadingText="Creating..."
            >
              Create API Key
            </Button>
          </VStack>
        )}
      </CardBody>
    </Card>
  );
}
