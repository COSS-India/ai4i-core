import {
  FormControl,
  FormErrorMessage,
  Input,
  NumberInput,
  NumberInputField,
  VStack,
} from "@chakra-ui/react";
import FormSection from "../common/FormSection";
import ReadOnlyField from "../common/ReadOnlyField";
import FieldHint from "../common/FieldHint";
import FieldLabel from "../common/FieldLabel";
import {
  TIER_RATE_LIMIT_PLATFORM_DEFAULT,
  formatModelTaskTypeLabel,
} from "../../config/constants";
import { FIELD_HINTS } from "../../config/fieldHints";
import { formatMonthlyQuota } from "../../utils/valueFormatters";
import type { TierFormData, TierFormQuota } from "../../types/tierManagement";
import { QuotaEditor } from "./QuotaEditor";
import { validateRateLimit } from "./tierFormValidation";

interface TierFormProps {
  readonly formData: TierFormData;
  readonly onChange: (data: TierFormData) => void;
  readonly taskTypeNames: string[];
  readonly unitByTaskType: Record<string, string>;
  readonly onSchedule?: (quota: TierFormQuota) => void;
  readonly onRemove?: (quota: TierFormQuota) => void;
  readonly removingTaskType?: string | null;
  readonly isEditMode?: boolean;
  readonly mode?: "create" | "edit" | "view";
  readonly showErrors?: boolean;
}

export function TierForm({
  formData,
  onChange,
  taskTypeNames,
  unitByTaskType,
  onSchedule,
  onRemove,
  removingTaskType,
  isEditMode,
  mode,
  showErrors,
}: TierFormProps) {
  const formMode = mode ?? (isEditMode ? "edit" : "create");
  const rateLimitError = validateRateLimit(formData.rateLimit);
  if (formMode === "view") {
    return (
      <>
        <FormSection title="Basic information">
          <ReadOnlyField label="Tier Name">{formData.name || "—"}</ReadOnlyField>
          <ReadOnlyField label="Description">{formData.description || "—"}</ReadOnlyField>
        </FormSection>
        <FormSection title="Usage limits">
          <ReadOnlyField label="Rate Limit (per minute)">
            {formData.rateLimit
              ? Number(formData.rateLimit).toLocaleString("en-US")
              : TIER_RATE_LIMIT_PLATFORM_DEFAULT}
          </ReadOnlyField>
          {formData.quotas.length ? (
            formData.quotas.map((q) => {
              const limit = Number(q.limit);
              return (
                <ReadOnlyField
                  key={q.modelTaskType}
                  label={formatModelTaskTypeLabel(q.modelTaskType)}
                >
                  {formatMonthlyQuota(Number.isFinite(limit) ? limit : 0, q.unit)}
                </ReadOnlyField>
              );
            })
          ) : (
            <ReadOnlyField label="Quotas">—</ReadOnlyField>
          )}
        </FormSection>
      </>
    );
  }

  return (
    <VStack align="stretch" spacing={0}>
      <VStack align="stretch" spacing={4}>
      <FormControl isRequired>
        <FieldLabel>Tier Name</FieldLabel>
        <Input
          value={formData.name}
          onChange={(e) => onChange({ ...formData, name: e.target.value })}
          placeholder={FIELD_HINTS.tier.name.placeholder}
          maxLength={100}
        />
        <FieldHint>{FIELD_HINTS.tier.name.helper}</FieldHint>
      </FormControl>

      <FormControl>
        <FieldLabel>Description</FieldLabel>
        <Input
          value={formData.description}
          onChange={(e) =>
            onChange({ ...formData, description: e.target.value })
          }
          placeholder={FIELD_HINTS.tier.description.placeholder}
        />
        <FieldHint>{FIELD_HINTS.tier.description.helper}</FieldHint>
      </FormControl>
      </VStack>

      <FormSection title="Usage limits">
      <FormControl isInvalid={!!rateLimitError}>
        <FieldLabel>Rate Limit (per minute)</FieldLabel>
        <NumberInput
          min={1}
          step={1}
          // Keep an out-of-range value on blur so the inline error can name it.
          clampValueOnBlur={false}
          value={formData.rateLimit}
          onChange={(v) => onChange({ ...formData, rateLimit: v })}
        >
          <NumberInputField placeholder={FIELD_HINTS.tier.rateLimit.placeholder} />
        </NumberInput>
        <FormErrorMessage>{rateLimitError}</FormErrorMessage>
        <FieldHint show={!rateLimitError}>{FIELD_HINTS.tier.rateLimit.helper}</FieldHint>
      </FormControl>

      <QuotaEditor
        quotas={formData.quotas}
        onChange={(quotas) => onChange({ ...formData, quotas })}
        taskTypeNames={taskTypeNames}
        unitByTaskType={unitByTaskType}
        onSchedule={onSchedule}
        onRemove={onRemove}
        removingTaskType={removingTaskType}
        isEditMode={isEditMode}
        showErrors={showErrors}
      />
      </FormSection>
    </VStack>
  );
}
