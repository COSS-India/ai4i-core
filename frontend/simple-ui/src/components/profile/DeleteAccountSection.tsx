import React from "react";
import {
  Alert,
  AlertDescription,
  AlertIcon,
  Box,
  Button,
  CloseButton,
  Divider,
  Heading,
  Text,
  VStack,
  useColorModeValue,
} from "@chakra-ui/react";
import type { User } from "../../types/auth";
import { canSelfDeleteAccount } from "../../utils/rbac";
import DeleteAccountModal from "./DeleteAccountModal";
import { useDeleteAccount } from "./hooks/useDeleteAccount";

interface DeleteAccountSectionProps {
  user: User;
}

export default function DeleteAccountSection({ user }: Readonly<DeleteAccountSectionProps>) {
  const dangerBg = useColorModeValue("red.50", "red.900");
  const dangerBorder = useColorModeValue("red.200", "red.700");
  const deleteAccount = useDeleteAccount(user);

  if (!canSelfDeleteAccount(user.roles)) {
    return null;
  }

  return (
    <>
      <Divider my={6} />

      <VStack spacing={4} align="stretch">
        <Box>
          <Heading size="sm" color="gray.700" userSelect="none" cursor="default">
            Delete Account
          </Heading>
          <Text fontSize="sm" color="gray.500" mt={1}>
            Once deleted, your account and access to the platform cannot be restored.
          </Text>
        </Box>

        {deleteAccount.soleAdminBlockMessage && (
          <Alert status="warning" borderRadius="md">
            <AlertIcon />
            <Box flex="1">
              <AlertDescription fontSize="sm">
                {deleteAccount.soleAdminBlockMessage}
              </AlertDescription>
            </Box>
            <CloseButton
              alignSelf="flex-start"
              position="relative"
              right={-1}
              top={-1}
              onClick={deleteAccount.dismissSoleAdminBlock}
              aria-label="Dismiss message"
            />
          </Alert>
        )}

        <Box
          bg={dangerBg}
          borderRadius="md"
          p={4}
          borderWidth="1px"
          borderColor={dangerBorder}
        >
          <Text fontSize="sm" color="gray.700" mb={4}>
            Deleting your account permanently removes your profile, login details,
            and activity history. You will lose access to all features and services
            associated with this account.
          </Text>
          <Button
            colorScheme="red"
            onClick={deleteAccount.handleOpenDeleteModal}
            isLoading={deleteAccount.isCheckingEligibility}
            loadingText="Checking..."
          >
            Delete Account
          </Button>
        </Box>
      </VStack>

      <DeleteAccountModal
        isOpen={deleteAccount.isModalOpen}
        onClose={deleteAccount.closeModal}
        onConfirm={deleteAccount.handleConfirmDelete}
        isConfirmLoading={deleteAccount.isDeleting}
      />
    </>
  );
}
