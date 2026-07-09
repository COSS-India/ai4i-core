import React, { useEffect, useMemo, useState } from "react";
import {
  Box,
  Card,
  CardBody,
  CardHeader,
  Heading,
  HStack,
  Text,
  VStack,
  useColorModeValue,
  Spinner,
  Center,
  Alert,
  AlertIcon,
  AlertDescription,
  Badge,
  Tooltip,
} from "@chakra-ui/react";
import type { APIKeyResponse } from "../../types/auth";
import { useAuth } from "../../hooks/useAuth";
import * as tenantService from "../../services/tenantService";
import {
  API_KEY,
  type ApiKeyAccessContext,
  formatApiKeyDisplayStatusLabel,
  getApiKeyDisplayStatusColorScheme,
  getApiKeyInactiveReason,
  isApiKeyExpired,
  resolveApiKeyDisplayStatus,
} from "../../config/constants";

export interface ApiKeyTabProps {
  apiKeys: APIKeyResponse[];
  isFetchingApiKey: boolean;
  isLoadingApiKeys: boolean;
  onFetchApiKeys: () => Promise<void>;
}

export default function ApiKeyTab({
  apiKeys,
  isFetchingApiKey,
  isLoadingApiKeys,
  onFetchApiKeys,
}: ApiKeyTabProps) {
  const { user } = useAuth();
  const [tenantStatus, setTenantStatus] = useState<string | null>(null);
  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");
  const inputReadOnlyBg = useColorModeValue("gray.50", "gray.700");

  const apiKeyAccessContext = useMemo(
    (): ApiKeyAccessContext => ({
      userIsActive: user?.is_active,
      userTenantActive: user?.is_tenant_active,
      tenantStatus,
    }),
    [user?.is_active, user?.is_tenant_active, tenantStatus]
  );

  useEffect(() => {
    const tenantId = user?.tenant_id?.trim();
    if (!tenantId) {
      setTenantStatus(null);
      return;
    }
    void tenantService.getViewTenant(tenantId).then(
      (tenant) => setTenantStatus(tenant?.status ?? null),
      () => setTenantStatus(null)
    );
  }, [user?.tenant_id]);

  const sortedApiKeys = [...apiKeys].sort((a, b) => {
    const dateA = a.created_at ? new Date(a.created_at).getTime() : 0;
    const dateB = b.created_at ? new Date(b.created_at).getTime() : 0;
    return dateB - dateA;
  });

  return (
    <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
      <CardHeader>
        <HStack justify="space-between">
          <Heading size="md" color="gray.700" userSelect="none" cursor="default">
            API Keys
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
              {apiKeys.length > 0 ? (
                <Box>
                  <Text fontSize="sm" color="gray.600" mb={3}>
                    API keys are used for programmatic access (scripts, CI/CD, external integrations).
                    Frontend inference uses your JWT session token automatically.
                  </Text>
                  <VStack spacing={2} align="stretch">
                    {sortedApiKeys.map((key) => (
                      <Card
                        key={key.api_key ?? `id-${key.id ?? ""}-${key.key_name}`}
                        bg={inputReadOnlyBg}
                        borderColor={cardBorder}
                        borderWidth="1px"
                      >
                        <CardBody p={4}>
                          <VStack align="stretch" spacing={3}>
                            <HStack justify="space-between" align="flex-start">
                              <Text fontWeight="semibold">{key.key_name}</Text>
                              {(() => {
                                const displayStatus = resolveApiKeyDisplayStatus(
                                  key,
                                  apiKeyAccessContext
                                );
                                const inactiveReason =
                                  displayStatus === API_KEY.DISPLAY_STATUS.INACTIVE
                                    ? isApiKeyExpired(key.expires_at)
                                      ? "This API key has expired."
                                      : getApiKeyInactiveReason(apiKeyAccessContext)
                                    : null;
                                const badge = (
                                  <Badge
                                    colorScheme={getApiKeyDisplayStatusColorScheme(displayStatus)}
                                  >
                                    {formatApiKeyDisplayStatusLabel(displayStatus)}
                                  </Badge>
                                );
                                return inactiveReason ? (
                                  <Tooltip label={inactiveReason} placement="top" hasArrow>
                                    {badge}
                                  </Tooltip>
                                ) : (
                                  badge
                                );
                              })()}
                            </HStack>
                            {key.created_at && (
                              <Text fontSize="sm" color="gray.600">
                                Created: {new Date(key.created_at).toLocaleString()}
                              </Text>
                            )}
                            {key.expires_at && (
                              <Text fontSize="sm" color="gray.600">
                                Expires: {new Date(key.expires_at).toLocaleString()}
                              </Text>
                            )}
                            {key.permissions.length > 0 && (
                              <HStack flexWrap="wrap" spacing={2}>
                                <Text fontSize="xs" color="gray.500">Permissions:</Text>
                                {key.permissions.map((permName) => (
                                  <Badge key={permName} colorScheme="blue" fontSize="xs">
                                    {permName}
                                  </Badge>
                                ))}
                              </HStack>
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
