// CreateTenantModal

import {
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
  VStack,
} from "@chakra-ui/react";
import { EMAIL_AVAILABLE_MSG } from "../../../../utils/tenantEmailValidation";
import type { TenantTabContext } from "../types";

type Props = TenantTabContext;

export default function CreateTenantModal({ tm }: Props) {
  return (
<Modal isOpen={tm.isTenantModalOpen} onClose={tm.closeTenantModal} size="md">
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Create Tenant</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={3} align="stretch">
              <FormControl isInvalid={Boolean(tm.tenantFormErrors.organisation)} isRequired>
                <FormLabel>Organisation</FormLabel>
                <Input
                  value={tm.tenantForm.organisation}
                  onChange={(e) => tm.handleTenantOrganisationChange(e.target.value)}
                  onBlur={(e) => tm.handleTenantOrganisationBlur(e.target.value)}
                />
                <FormErrorMessage>{tm.tenantFormErrors.organisation}</FormErrorMessage>
              </FormControl>
              <FormControl isInvalid={Boolean(tm.tenantFormErrors.contact_name)} isRequired>
                <FormLabel>Contact Name</FormLabel>
                <Input
                  value={tm.tenantForm.contact_name}
                  onChange={(e) => tm.handleTenantContactNameChange(e.target.value)}
                />
                <FormErrorMessage>{tm.tenantFormErrors.contact_name}</FormErrorMessage>
              </FormControl>
              <FormControl isInvalid={Boolean(tm.tenantFormErrors.email)} isRequired>
                <FormLabel>Email</FormLabel>
                <Input
                  type="email"
                  value={tm.tenantForm.email}
                  onChange={(e) => tm.handleTenantEmailChange(e.target.value)}
                />
                <FormErrorMessage>{tm.tenantFormErrors.email}</FormErrorMessage>
                {tm.tenantEmailStatus === "checking" && !tm.tenantFormErrors.email && (
                  <FormHelperText color="gray.500">Checking if email exists…</FormHelperText>
                )}
                {tm.tenantEmailStatus === "available" && !tm.tenantFormErrors.email && (
                  <FormHelperText color="green.600">{EMAIL_AVAILABLE_MSG}</FormHelperText>
                )}
              </FormControl>
              <FormControl isInvalid={Boolean(tm.tenantFormErrors.phone_number)}>
                <FormLabel>Phone Number</FormLabel>
                <Input
                  value={tm.tenantForm.phone_number}
                  onChange={(e) => tm.handleTenantPhoneChange(e.target.value)}
                />
                <FormErrorMessage>{tm.tenantFormErrors.phone_number}</FormErrorMessage>
              </FormControl>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button mr={3} variant="ghost" onClick={tm.closeTenantModal}>
              Cancel
            </Button>
            <Button
              colorScheme="blue"
              onClick={tm.handleRegisterTenant}
              isLoading={tm.isSubmittingTenant}
              isDisabled={!tm.canSubmitTenantForm}
            >
              Create
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
  );
}
