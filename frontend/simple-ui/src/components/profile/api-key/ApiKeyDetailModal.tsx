import {
  Badge,
  Box,
  Button,
  HStack,
  SimpleGrid,
  Text,
} from "@chakra-ui/react";
import React from "react";
import StandardModal from "../../common/StandardModal";
import {
  formatApiKeyDisplayStatusLabel,
  getApiKeyDisplayStatusColorScheme,
  type ApiKeyDisplayStatusValue,
} from "../../../config/constants";
import type { AdminAPIKeyWithUserResponse } from "../../../types/auth";

export interface ApiKeyDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  apiKey: AdminAPIKeyWithUserResponse | null;
  formatPermission: (permissionId: number | string) => string;
  formatKeyId: (key: AdminAPIKeyWithUserResponse) => string;
  resolveKeyDisplayStatus: (key: AdminAPIKeyWithUserResponse) => ApiKeyDisplayStatusValue;
  getKeyInactiveReason: (key: AdminAPIKeyWithUserResponse) => string | null;
}

const ApiKeyDetailModal: React.FC<ApiKeyDetailModalProps> = ({
  isOpen,
  onClose,
  apiKey,
  formatPermission,
  formatKeyId,
  resolveKeyDisplayStatus,
  getKeyInactiveReason,
}) => (
  <StandardModal
    isOpen={isOpen}
    onClose={onClose}
    size="2xl"
    title="API Key Details"
    footer={<Button onClick={onClose}>Close</Button>}
    contentProps={{ maxW: "900px", maxH: "600px" }}
    bodyProps={{ overflowY: "auto" }}
  >
    {apiKey && (
      <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
        <Box>
          <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
            Key Name
          </Text>
          <Text fontSize="md">{apiKey.key_name}</Text>
        </Box>
        <Box>
          <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
            Key ID
          </Text>
          <Text fontSize="sm" fontFamily="mono" color="gray.700" wordBreak="break-all">
            {formatKeyId(apiKey)}
          </Text>
        </Box>
        <Box gridColumn={{ base: "span 1", md: "span 2" }}>
          <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={2}>
            Permissions
          </Text>
          {(apiKey.permissions ?? []).length > 0 ? (
            <HStack flexWrap="wrap" spacing={2}>
              {(apiKey.permissions ?? []).map((perm) => (
                <Badge key={String(perm)} colorScheme="blue" fontSize="sm" p={2}>
                  {formatPermission(perm)}
                </Badge>
              ))}
            </HStack>
          ) : (
            <Text fontSize="sm" color="gray.500">
              No permissions assigned
            </Text>
          )}
        </Box>
        <Box>
          <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
            Status
          </Text>
          <Badge
            colorScheme={getApiKeyDisplayStatusColorScheme(resolveKeyDisplayStatus(apiKey))}
            fontSize="sm"
            p={2}
          >
            {formatApiKeyDisplayStatusLabel(resolveKeyDisplayStatus(apiKey))}
          </Badge>
          {getKeyInactiveReason(apiKey) && (
            <Text fontSize="xs" color="gray.500" mt={2}>
              {getKeyInactiveReason(apiKey)}
            </Text>
          )}
        </Box>
        <Box>
          <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
            Created At
          </Text>
          <Text fontSize="sm">
            {apiKey.created_at ? new Date(apiKey.created_at).toLocaleString() : "—"}
          </Text>
        </Box>
        {apiKey.expires_at && (
          <Box>
            <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
              Expires At
            </Text>
            <Text fontSize="sm">{new Date(apiKey.expires_at).toLocaleString()}</Text>
          </Box>
        )}
        {apiKey.last_used && (
          <Box>
            <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
              Last Used
            </Text>
            <Text fontSize="sm">{new Date(apiKey.last_used).toLocaleString()}</Text>
          </Box>
        )}
      </SimpleGrid>
    )}
  </StandardModal>
);

export default ApiKeyDetailModal;
