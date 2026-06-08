import {
  Alert,
  AlertDescription,
  AlertIcon,
  Box,
  Button,
  Checkbox,
  CheckboxGroup,
  FormControl,
  FormLabel,
  Input,
  SimpleGrid,
  Text,
  VStack,
} from "@chakra-ui/react";
import React from "react";
import StandardModal from "../../common/StandardModal";
import type { AdminAPIKeyWithUserResponse, APIKeyUpdate, Permission } from "../../../types/auth";

export interface ApiKeyUpdateModalProps {
  isOpen: boolean;
  onClose: () => void;
  selectedKey: AdminAPIKeyWithUserResponse | null;
  formData: APIKeyUpdate;
  onFormChange: (data: APIKeyUpdate) => void;
  permissions: Permission[];
  onSubmit: () => void;
  isUpdating: boolean;
}

const ApiKeyUpdateModal: React.FC<ApiKeyUpdateModalProps> = ({
  isOpen,
  onClose,
  selectedKey,
  formData,
  onFormChange,
  permissions,
  onSubmit,
  isUpdating,
}) => (
  <StandardModal
    isOpen={isOpen}
    onClose={onClose}
    size="lg"
    title="Update API Key"
    footer={
      <>
        <Button variant="ghost" mr={3} onClick={onClose} isDisabled={isUpdating}>
          Cancel
        </Button>
        <Button
          colorScheme="blue"
          onClick={onSubmit}
          isLoading={isUpdating}
          loadingText="Updating..."
          isDisabled={
            isUpdating ||
            !(formData.key_name ?? "").trim() ||
            !(formData.permissions?.length ?? 0)
          }
        >
          Update
        </Button>
      </>
    }
  >
    <VStack spacing={4} align="stretch">
      <FormControl>
        <FormLabel fontWeight="semibold">Key Name</FormLabel>
        <Input
          value={formData.key_name || ""}
          onChange={(e) => onFormChange({ ...formData, key_name: e.target.value })}
          bg="white"
        />
      </FormControl>
      <FormControl>
        <FormLabel fontWeight="semibold">Permissions</FormLabel>
        <Text fontSize="sm" color="gray.600" mb={3}>
          Select permissions for this API key
        </Text>
        {permissions.length > 0 ? (
          <Box borderWidth="1px" borderRadius="md" p={4} bg="white" maxH="300px" overflowY="auto">
            <CheckboxGroup
              value={formData.permissions || []}
              onChange={(values) =>
                onFormChange({ ...formData, permissions: values as string[] })
              }
            >
              <SimpleGrid columns={2} spacing={3}>
                {permissions.map((perm) => (
                  <Checkbox key={perm.name} value={perm.name} colorScheme="blue">
                    <Text fontSize="sm">{perm.name}</Text>
                  </Checkbox>
                ))}
              </SimpleGrid>
            </CheckboxGroup>
          </Box>
        ) : (
          <Alert status="info" borderRadius="md">
            <AlertIcon />
            <AlertDescription>
              Click &quot;Load Permissions&quot; in the Permissions tab to view available
              permissions
            </AlertDescription>
          </Alert>
        )}
      </FormControl>
      {selectedKey?.api_key && (
        <Text fontSize="xs" color="gray.500">
          Key: {selectedKey.api_key.slice(0, 8)}…{selectedKey.api_key.slice(-4)}
        </Text>
      )}
    </VStack>
  </StandardModal>
);

export default ApiKeyUpdateModal;
