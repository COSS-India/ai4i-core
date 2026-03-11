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
  Spinner,
  Center,
  Alert,
  AlertIcon,
  AlertDescription,
  Checkbox,
  Badge,
} from "@chakra-ui/react";
import { ViewIcon, ViewOffIcon, CopyIcon } from "@chakra-ui/icons";
import { useApiKey } from "../../hooks/useApiKey";
import { useSessionExpiry } from "../../hooks/useSessionExpiry";
import { useApiKeyTab } from "./hooks/useApiKeyTab";
import type { APIKeyResponse } from "../../types/auth";

export interface ApiKeyTabProps {
  apiKeys: APIKeyResponse[];
  selectedApiKeyId: number | null;
  setSelectedApiKeyId: (id: number | null) => void;
  isFetchingApiKey: boolean;
  isLoadingApiKeys: boolean;
  onFetchApiKeys: () => Promise<void>;
}

export default function ApiKeyTab({
  apiKeys,
  selectedApiKeyId,
  setSelectedApiKeyId,
  isFetchingApiKey,
  isLoadingApiKeys,
  onFetchApiKeys,
}: ApiKeyTabProps) {
  const { getApiKey, setApiKey } = useApiKey();
  const { checkSessionExpiry } = useSessionExpiry();
  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");
  const inputReadOnlyBg = useColorModeValue("gray.50", "gray.700");

  const apiKey = getApiKey();
  const maskedApiKey = apiKey ? "****" + apiKey.slice(-4) : "";

  const tab = useApiKeyTab({
    getApiKey,
    setApiKey,
    setSelectedApiKeyId,
    checkSessionExpiry,
  });

  const sortedApiKeys = [...apiKeys].sort((a, b) => {
    const dateA = new Date(a.created_at).getTime();
    const dateB = new Date(b.created_at).getTime();
    return dateB - dateA;
  });

  return (
    <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
      <CardHeader>
        <HStack justify="space-between">
          <Heading size="md" color="gray.700" userSelect="none" cursor="default">
            API Key
          </Heading>
          {isFetchingApiKey && <Spinner size="sm" color="blue.500" />}
        </HStack>
      </CardHeader>
      <CardBody>
        <VStack spacing={4} align="stretch">
          {isFetchingApiKey ? (
            <Center py={8}>
              <VStack spacing={4}>
                <Spinner size="lg" color="blue.500" />
                <Text color="gray.600">Loading API keys...</Text>
              </VStack>
            </Center>
          ) : (
            <>
              {(apiKeys.length > 0 || isLoadingApiKeys) && (
                <FormControl>
                  <FormLabel fontWeight="semibold">Your API Key</FormLabel>
                  <InputGroup>
                    <Input
                      type={tab.showApiKey ? "text" : "password"}
                      value={tab.showApiKey ? (apiKey || "") : maskedApiKey}
                      isReadOnly
                      bg={inputReadOnlyBg}
                      placeholder={apiKey ? undefined : "Select a key below to use it"}
                    />
                    <InputRightElement width="8rem">
                      <HStack spacing={1}>
                        <IconButton
                          aria-label={tab.showApiKey ? "Hide API key" : "Show API key"}
                          icon={tab.showApiKey ? <ViewOffIcon /> : <ViewIcon />}
                          onClick={() => tab.setShowApiKey(!tab.showApiKey)}
                          variant="ghost"
                          size="sm"
                          isDisabled={!apiKey}
                        />
                        {apiKey && (
                          <IconButton
                            aria-label="Copy API key"
                            icon={<CopyIcon />}
                            onClick={tab.handleCopyApiKey}
                            variant="ghost"
                            size="sm"
                          />
                        )}
                      </HStack>
                    </InputRightElement>
                  </InputGroup>
                </FormControl>
              )}

              {apiKeys.length > 0 ? (
                <Box>
                  <Heading size="sm" mb={4} color="gray.700" userSelect="none" cursor="default">
                    Your API Keys ({apiKeys.length})
                  </Heading>
                  <Text fontSize="sm" color="gray.600" mb={3}>
                    Select an API key to use it as your current key
                  </Text>
                  <VStack spacing={2} align="stretch">
                    {sortedApiKeys.map((key) => (
                      <Card
                        key={key.id}
                        bg={inputReadOnlyBg}
                        borderColor={selectedApiKeyId === key.id ? "blue.500" : cardBorder}
                        borderWidth={selectedApiKeyId === key.id ? "2px" : "1px"}
                      >
                        <CardBody p={4}>
                          <VStack align="stretch" spacing={3}>
                            <HStack justify="space-between" align="flex-start">
                              <HStack spacing={3} flex={1}>
                                <Checkbox
                                  isChecked={selectedApiKeyId === key.id}
                                  onChange={(e) => {
                                    if (e.target.checked) {
                                      tab.handleSelectApiKey(key);
                                    } else {
                                      tab.handleUnselectApiKey();
                                    }
                                  }}
                                  colorScheme="blue"
                                  size="lg"
                                >
                                  <Box>
                                    <Text fontWeight="semibold">{key.key_name}</Text>
                                  </Box>
                                </Checkbox>
                              </HStack>
                              <Badge colorScheme={key.is_active ? "green" : "red"}>
                                {key.is_active ? "Active" : "Inactive"}
                              </Badge>
                            </HStack>
                            <Text fontSize="sm" color="gray.600">
                              Created: {new Date(key.created_at).toLocaleString()}
                            </Text>
                            {key.expires_at && (
                              <Text fontSize="sm" color="gray.600">
                                Expires: {new Date(key.expires_at).toLocaleString()}
                              </Text>
                            )}
                            {key.permissions.length > 0 && (
                              <HStack flexWrap="wrap" spacing={2}>
                                <Text fontSize="xs" color="gray.500">Permissions:</Text>
                                {key.permissions.map((perm) => (
                                  <Badge key={perm} colorScheme="blue" fontSize="xs">
                                    {perm}
                                  </Badge>
                                ))}
                              </HStack>
                            )}
                            {key.key_value && (
                              <Alert status="info" borderRadius="md" mt={2}>
                                <AlertIcon />
                                <AlertDescription fontSize="xs">
                                  Key value is only shown once. Make sure to save it securely.
                                </AlertDescription>
                              </Alert>
                            )}
                          </VStack>
                        </CardBody>
                      </Card>
                    ))}
                  </VStack>
                </Box>
              ) : !isLoadingApiKeys ? (
                <Alert status="info" borderRadius="md">
                  <AlertIcon />
                  <AlertDescription>
                    <Text fontWeight="semibold" mb={2}>
                      No API keys found
                    </Text>
                    <Text fontSize="sm">
                      You don&apos;t have any API keys yet. To get an API key, please contact your administrator to add the necessary permissions to your account.
                    </Text>
                  </AlertDescription>
                </Alert>
              ) : null}
            </>
          )}
        </VStack>
      </CardBody>
    </Card>
  );
}
