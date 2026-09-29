import {
  Alert,
  AlertDescription,
  AlertIcon,
  FormControl,
  FormErrorMessage,
  HStack,
  Input,
  InputGroup,
  InputLeftAddon,
  VStack,
} from "@chakra-ui/react";
import TierSelect from "./TierSelect";
import FieldHint from "../common/FieldHint";
import FieldLabel from "../common/FieldLabel";
import FormActions from "../common/FormActions";
import StandardModal from "../common/StandardModal";
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
    <StandardModal
      isOpen={isOpen}
      onClose={form.close}
      size="xl"
      scrollBehavior="inside"
      title="Assign Tier"
      description={
        tenant
          ? `Assign a tier and budget window for ${tenant.organisation}.`
          : "Assign a tier and budget window."
      }
      modalProps={{ blockScrollOnMount: true }}
      headerProps={{ px: 6, pt: 5, pb: 4 }}
      bodyProps={{ px: 6, py: 5 }}
      footerProps={{ px: 6, py: 4 }}
      footer={
        <FormActions
          submitLabel="Assign"
          onCancel={form.close}
          onSubmit={form.submit}
          isLoading={form.isAssigning}
          loadingText="Assigning..."
          justify="space-between"
          pt={0}
        />
      }
    >
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
          <FieldLabel>Tier</FieldLabel>
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
          <FieldLabel>Budget</FieldLabel>
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
            <FieldLabel>Budget Effective From</FieldLabel>
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
            <FieldLabel>Budget Effective To</FieldLabel>
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
    </StandardModal>
  );
}
