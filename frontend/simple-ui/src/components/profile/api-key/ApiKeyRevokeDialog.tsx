import {
  Alert,
  AlertDescription,
  AlertIcon,
  AlertDialog,
  AlertDialogBody,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogOverlay,
  Badge,
  Box,
  Button,
  HStack,
  Text,
  VStack,
} from "@chakra-ui/react";
import React, { RefObject } from "react";
import type { AdminAPIKeyWithUserResponse } from "../../../types/auth";

export interface ApiKeyRevokeDialogProps {
  isOpen: boolean;
  onClose: () => void;
  apiKey: AdminAPIKeyWithUserResponse | null;
  formatPermission: (permissionId: number | string) => string;
  onConfirm: () => void;
  isRevoking: boolean;
  cancelRef: RefObject<HTMLButtonElement>;
}

const ApiKeyRevokeDialog: React.FC<ApiKeyRevokeDialogProps> = ({
  isOpen,
  onClose,
  apiKey,
  formatPermission,
  onConfirm,
  isRevoking,
  cancelRef,
}) => (
  <AlertDialog isOpen={isOpen} leastDestructiveRef={cancelRef} onClose={onClose}>
    <AlertDialogOverlay>
      <AlertDialogContent>
        <AlertDialogHeader fontSize="lg" fontWeight="bold">
          Revoke API Key
        </AlertDialogHeader>
        <AlertDialogBody>
          <VStack align="stretch" spacing={3}>
            <Text>
              Are you sure you want to revoke the API key &quot;{apiKey?.key_name}&quot;?
            </Text>
            <Box>
              <Text fontWeight="semibold" fontSize="sm" color="gray.700" mb={2}>
                Key Details:
              </Text>
              <VStack align="start" spacing={1} fontSize="sm">
                <Text>
                  <strong>Key:</strong>{" "}
                  {apiKey?.api_key
                    ? `${apiKey.api_key.slice(0, 8)}…${apiKey.api_key.slice(-4)}`
                    : apiKey?.id != null
                      ? String(apiKey.id)
                      : "—"}
                </Text>
                <Text>
                  <strong>Created:</strong>{" "}
                  {apiKey?.created_at
                    ? new Date(apiKey.created_at).toLocaleString()
                    : "N/A"}
                </Text>
              </VStack>
            </Box>
            {apiKey && (apiKey.permissions ?? []).length > 0 && (
              <Box>
                <Text fontWeight="semibold" fontSize="sm" color="gray.700" mb={2}>
                  Permissions (will be revoked):
                </Text>
                <HStack flexWrap="wrap" spacing={2}>
                  {(apiKey.permissions ?? []).map((perm) => (
                    <Badge key={String(perm)} colorScheme="orange" fontSize="xs">
                      {formatPermission(perm)}
                    </Badge>
                  ))}
                </HStack>
              </Box>
            )}
            <Alert status="warning" borderRadius="md" mt={2}>
              <AlertIcon />
              <AlertDescription fontSize="sm">
                This action will revoke the API key. Revoked keys cannot be reactivated.
              </AlertDescription>
            </Alert>
          </VStack>
        </AlertDialogBody>
        <AlertDialogFooter>
          <Button ref={cancelRef} onClick={onClose} isDisabled={isRevoking}>
            Cancel
          </Button>
          <Button
            colorScheme="red"
            onClick={onConfirm}
            ml={3}
            isLoading={isRevoking}
            loadingText="Revoking..."
          >
            Revoke
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialogOverlay>
  </AlertDialog>
);

export default ApiKeyRevokeDialog;
