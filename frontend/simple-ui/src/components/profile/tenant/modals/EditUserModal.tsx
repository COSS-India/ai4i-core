// EditUserModal

import {
  Box,
  Button,
  FormControl,
  FormErrorMessage,
  FormHelperText,
  FormLabel,
  Input,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalOverlay,
  Select,
  Text,
  VStack,
} from "@chakra-ui/react";
import { EMAIL_AVAILABLE_MSG } from "../../../../utils/tenantEmailValidation";
import { TENANT_USER_ROLE_OPTIONS } from "../../types";
import type { TenantTabContext } from "../types";
import { dash } from "../utils";

type Props = TenantTabContext;

export default function EditUserModal({ tm }: Props) {
  return (
<Modal
        isOpen={tm.isEditUserModalOpen}
        onClose={tm.closeEditUserModal}
        size="md"
      >
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Edit User</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={3} align="stretch">
              <FormControl isRequired isInvalid={Boolean(tm.editUserFormErrors.username)}>
                <FormLabel>Username</FormLabel>
                <Input
                  value={tm.editUserForm.username ?? ""}
                  onChange={(e) => tm.handleEditUserUsernameChange(e.target.value)}
                />
                <FormErrorMessage>{tm.editUserFormErrors.username}</FormErrorMessage>
              </FormControl>
              <FormControl>
                <FormLabel>Email</FormLabel>
                <Text fontSize="md" color="gray.700" py={1}>
                  {dash(tm.editUserRow?.email)}
                </Text>
                <Text fontSize="xs" color="gray.500" mt={1}>
                  Email cannot be changed. Suspend or delete the account if the user has left the
                  organisation.
                </Text>
              </FormControl>
              <FormControl isInvalid={Boolean(tm.editUserFormErrors.full_name)}>
                <FormLabel>Full Name</FormLabel>
                <Input
                  value={tm.editUserForm.full_name ?? ""}
                  onChange={(e) => tm.handleEditUserFullNameChange(e.target.value)}
                />
                <FormErrorMessage>{tm.editUserFormErrors.full_name}</FormErrorMessage>
              </FormControl>
              <FormControl isRequired>
                <FormLabel>Role</FormLabel>
                <Select
                  value={tm.editUserForm.role}
                  onChange={(e) =>
                    tm.setEditUserForm({
                      ...tm.editUserForm,
                      role: e.target.value as typeof tm.editUserForm.role,
                    })
                  }
                >
                  {TENANT_USER_ROLE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </Select>
              </FormControl>
              <FormControl isInvalid={Boolean(tm.editUserFormErrors.phone_number)}>
                <FormLabel>Phone Number</FormLabel>
                <Input
                  value={tm.editUserForm.phone_number ?? ""}
                  onChange={(e) => tm.handleEditUserPhoneChange(e.target.value)}
                />
                <FormErrorMessage>{tm.editUserFormErrors.phone_number}</FormErrorMessage>
              </FormControl>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button mr={3} variant="ghost" onClick={tm.closeEditUserModal}>
              Cancel
            </Button>
            <Button
              colorScheme="blue"
              onClick={tm.handleSaveEditUser}
              isLoading={tm.isSubmittingEditUser}
              isDisabled={!tm.canSubmitEditUserForm}
            >
              Save
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
  );
}
