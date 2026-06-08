// AddUserModal

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

type Props = TenantTabContext;

export default function AddUserModal({ tm, isAdmin }: Props) {
  return (
<Modal isOpen={tm.isUserModalOpen} onClose={tm.closeUserModal} size="md">
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Add Tenant User</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={3} align="stretch">
              {isAdmin && tm.lockedUserFormTenantId && (
                <FormControl isRequired isInvalid={Boolean(tm.userFormErrors.tenant_id)}>
                  <FormLabel>Tenant</FormLabel>
                  <Input
                    value={tm.getLockedUserFormTenantLabel()}
                    isReadOnly
                    bg="gray.50"
                    _dark={{ bg: "whiteAlpha.100" }}
                    cursor="not-allowed"
                  />
                  <FormErrorMessage>{tm.userFormErrors.tenant_id}</FormErrorMessage>
                </FormControl>
              )}
              {isAdmin && !tm.lockedUserFormTenantId && (
                <FormControl isRequired isInvalid={Boolean(tm.userFormErrors.tenant_id)}>
                  <FormLabel>Tenant</FormLabel>
                  <Select
                    value={tm.userForm.tenant_id}
                    onChange={(e) => tm.setUserFormTenantId(e.target.value)}
                  >
                    <option value="">Select a tenant…</option>
                    {tm.tenants.map((t) => (
                      <option key={t.tenant_id} value={t.tenant_id}>
                        {t.organisation}
                      </option>
                    ))}
                  </Select>
                  <FormErrorMessage>{tm.userFormErrors.tenant_id}</FormErrorMessage>
                </FormControl>
              )}
              <FormControl isRequired isInvalid={Boolean(tm.userFormErrors.email)}>
                <FormLabel>Email</FormLabel>
                <Input
                  type="email"
                  value={tm.userForm.email}
                  onChange={(e) => tm.handleUserEmailChange(e.target.value)}
                />
                <FormErrorMessage>{tm.userFormErrors.email}</FormErrorMessage>
                {tm.userEmailStatus === "checking" && !tm.userFormErrors.email && (
                  <FormHelperText color="gray.500">Checking if email exists…</FormHelperText>
                )}
                {tm.userEmailStatus === "available" && !tm.userFormErrors.email && (
                  <FormHelperText color="green.600">{EMAIL_AVAILABLE_MSG}</FormHelperText>
                )}
              </FormControl>
              <FormControl isRequired isInvalid={Boolean(tm.userFormErrors.full_name)}>
                <FormLabel>Full Name</FormLabel>
                <Input
                  value={tm.userForm.full_name}
                  onChange={(e) => tm.handleUserFullNameChange(e.target.value)}
                />
                <FormErrorMessage>{tm.userFormErrors.full_name}</FormErrorMessage>
              </FormControl>
              <FormControl isRequired>
                <FormLabel>Role</FormLabel>
                <Select
                  value={tm.userForm.role}
                  onChange={(e) =>
                    tm.setUserForm({
                      ...tm.userForm,
                      role: e.target.value as typeof tm.userForm.role,
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
              <FormControl isInvalid={Boolean(tm.userFormErrors.phone_number)}>
                <FormLabel>Phone Number</FormLabel>
                <Input
                  value={tm.userForm.phone_number}
                  onChange={(e) => tm.handleUserPhoneChange(e.target.value)}
                />
                <FormErrorMessage>{tm.userFormErrors.phone_number}</FormErrorMessage>
              </FormControl>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button mr={3} variant="ghost" onClick={tm.closeUserModal}>
              Cancel
            </Button>
            <Button
              colorScheme="blue"
              onClick={tm.handleRegisterUser}
              isLoading={tm.isSubmittingUser}
              isDisabled={!tm.canSubmitUserForm}
            >
              Add
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
  );
}
