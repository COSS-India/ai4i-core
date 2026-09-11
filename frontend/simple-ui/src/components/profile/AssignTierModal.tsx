import {
  Alert,
  AlertDescription,
  AlertIcon,
  Button,
  FormControl,
  FormErrorMessage,
  FormLabel,
  HStack,
  Input,
  InputGroup,
  InputLeftAddon,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalOverlay,
  VStack,
} from "@chakra-ui/react";
import TierSelect from "./TierSelect";
import FieldHint from "../common/FieldHint";
import { FIELD_HINTS } from "../../config/fieldHints";
import { useAssignTier } from "./hooks/useAssignTier";
import type { ServiceMappingsStatus } from "./types";
import type { Tier } from "../../types/tierManagement";
import type { TenantView } from "../../types/tenant";

export interface AssignTierModalProps {
  isOpen: boolean;
  onClose: () => void;
  tenant: TenantView | null;
  tierOptions: Tier[];
  /** Tier ids with at least one service mapped. */
  tierIdsWithServices: Set<string>;
  serviceMappingsStatus: ServiceMappingsStatus;
  noServicesMessage: string;
  onAssigned: (tenantId: string) => Promise<void> | void;
}

export default function AssignTierModal({
  isOpen,
  onClose,
  tenant,
  tierOptions,
  tierIdsWithServices,
  serviceMappingsStatus,
  noServicesMessage,
  onAssigned,
}: Readonly<AssignTierModalProps>) {
  const form = useAssignTier({
    isOpen,
    tenant,
    serviceMappingsStatus,
    tierIdsWithServices,
    noServicesMessage,
    onAssigned,
    onClose,
  });

  const { values, errors } = form;
  const tierInvalid = !!errors.tier || form.showTierNoServices;

  return (
    <Modal isOpen={isOpen} onClose={form.close} isCentered size="xl">
      <ModalOverlay />
      <ModalContent minH="350px">
        <ModalHeader fontSize="md" fontWeight="semibold" pb={1}>
          Assign Tier{tenant ? ` — ${tenant.organisation}` : ""}
        </ModalHeader>
        <ModalCloseButton isDisabled={form.isAssigning} />
        <ModalBody pb={6}>
          <VStack align="stretch" spacing={5}>
            {form.submitError && (
              <Alert status="error" borderRadius="md">
                <AlertIcon />
                <AlertDescription fontSize="sm">
                  {form.submitError}
                </AlertDescription>
              </Alert>
            )}

            <FormControl isRequired isInvalid={tierInvalid}>
              <FormLabel fontWeight="semibold" fontSize="sm">
                Tier
              </FormLabel>
              <TierSelect
                value={values.tierId}
                onChange={form.setTierId}
                tierOptions={tierOptions}
                serviceMappingsReady={serviceMappingsStatus === "ready"}
                tierIdsWithServices={tierIdsWithServices}
                isDisabled={form.isAssigning}
                isInvalid={tierInvalid}
              />
              <FormErrorMessage fontSize="xs">
                {errors.tier ?? noServicesMessage}
              </FormErrorMessage>
            </FormControl>

            <FormControl isRequired isInvalid={!!errors.budget}>
              <FormLabel fontWeight="semibold" fontSize="sm">
                Budget
              </FormLabel>
              <InputGroup size="sm">
                <InputLeftAddon>₹</InputLeftAddon>
                <Input
                  value={values.budget}
                  onChange={(e) => form.setBudget(e.target.value)}
                  placeholder={FIELD_HINTS.assignTier.budget.placeholder}
                  inputMode="decimal"
                  isDisabled={form.isAssigning}
                />
              </InputGroup>
              <FormErrorMessage fontSize="xs">{errors.budget}</FormErrorMessage>
              <FieldHint show={!errors.budget}>
                {FIELD_HINTS.assignTier.budget.helper}
              </FieldHint>
            </FormControl>

            <HStack spacing={4} align="flex-start">
              <FormControl isRequired isInvalid={!!errors.effectiveFrom}>
                <FormLabel fontWeight="semibold" fontSize="sm">
                  Budget Effective From
                </FormLabel>
                <Input
                  type="date"
                  size="sm"
                  value={values.effectiveFrom}
                  min={form.today}
                  onChange={(e) => form.setEffectiveFrom(e.target.value)}
                  isDisabled={form.isAssigning}
                />
                <FormErrorMessage fontSize="xs">
                  {errors.effectiveFrom}
                </FormErrorMessage>
                <FieldHint show={!errors.effectiveFrom}>
                  {FIELD_HINTS.assignTier.effectiveFrom.helper}
                </FieldHint>
              </FormControl>

              <FormControl isRequired isInvalid={!!errors.effectiveTo}>
                <FormLabel fontWeight="semibold" fontSize="sm">
                  Budget Effective To
                </FormLabel>
                <Input
                  type="date"
                  size="sm"
                  value={values.effectiveTo}
                  min={form.effectiveToMin}
                  onChange={(e) => form.setEffectiveTo(e.target.value)}
                  isDisabled={form.isAssigning}
                />
                <FormErrorMessage fontSize="xs">
                  {errors.effectiveTo}
                </FormErrorMessage>
                <FieldHint show={!errors.effectiveTo}>
                  {FIELD_HINTS.assignTier.effectiveTo.helper}
                </FieldHint>
              </FormControl>
            </HStack>
          </VStack>
        </ModalBody>
        <ModalFooter>
          <Button
            variant="ghost"
            mr={3}
            onClick={form.close}
            isDisabled={form.isAssigning}
          >
            Cancel
          </Button>
          <Button
            colorScheme="blue"
            isLoading={form.isAssigning}
            loadingText="Assigning..."
            onClick={form.submit}
          >
            Assign
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
