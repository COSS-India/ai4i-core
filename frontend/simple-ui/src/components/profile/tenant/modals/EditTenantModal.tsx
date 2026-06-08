// EditTenantModal

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
import type { TenantTabContext } from "../types";

type Props = TenantTabContext;

export default function EditTenantModal({ tm }: Props) {
  return (
<Modal
        isOpen={tm.isEditTenantModalOpen}
        onClose={tm.closeEditTenantModal}
        size="md"
      >
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Edit Tenant</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={3} align="stretch">
              <FormControl
                isRequired
                isInvalid={Boolean(tm.editTenantFormErrors.organisation)}
              >
                <FormLabel>Organisation</FormLabel>
                <Input
                  value={tm.editTenantForm.organisation ?? ""}
                  onChange={(e) => tm.handleEditTenantOrganisationChange(e.target.value)}
                  onBlur={(e) => tm.handleEditTenantOrganisationBlur(e.target.value)}
                />
                <FormErrorMessage>{tm.editTenantFormErrors.organisation}</FormErrorMessage>
              </FormControl>
              <FormControl isInvalid={Boolean(tm.editTenantFormErrors.contact_name)}>
                <FormLabel>Contact Name</FormLabel>
                <Input
                  value={tm.editTenantForm.contact_name ?? ""}
                  onChange={(e) => tm.handleEditTenantContactNameChange(e.target.value)}
                />
                <FormErrorMessage>{tm.editTenantFormErrors.contact_name}</FormErrorMessage>
              </FormControl>
              <FormControl isRequired isInvalid={Boolean(tm.editTenantFormErrors.email)}>
                <FormLabel>Email</FormLabel>
                <Input
                  type="email"
                  value={tm.editTenantForm.email ?? ""}
                  onChange={(e) => tm.handleEditTenantEmailChange(e.target.value)}
                />
                <FormErrorMessage>{tm.editTenantFormErrors.email}</FormErrorMessage>
                {tm.editTenantEmailStatus === "checking" && !tm.editTenantFormErrors.email && (
                  <FormHelperText color="gray.500">Checking if email exists…</FormHelperText>
                )}
                {tm.editTenantEmailStatus === "available" && !tm.editTenantFormErrors.email && (
                  <FormHelperText color="green.600">{EMAIL_AVAILABLE_MSG}</FormHelperText>
                )}
                <FormHelperText>
                  If you change the contact email, the update takes effect only after the new
                  address is verified.
                </FormHelperText>
              </FormControl>
              <FormControl isInvalid={Boolean(tm.editTenantFormErrors.phone_number)}>
                <FormLabel>Phone Number</FormLabel>
                <Input
                  value={tm.editTenantForm.phone_number ?? ""}
                  onChange={(e) => tm.handleEditTenantPhoneChange(e.target.value)}
                />
                <FormErrorMessage>{tm.editTenantFormErrors.phone_number}</FormErrorMessage>
              </FormControl>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button mr={3} variant="ghost" onClick={tm.closeEditTenantModal}>
              Cancel
            </Button>
            <Button
              colorScheme="blue"
              onClick={tm.handleSaveEditTenant}
              isLoading={tm.isSubmittingEditTenant}
              isDisabled={!tm.canSubmitEditTenantForm}
            >
              Save
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
  );
}
