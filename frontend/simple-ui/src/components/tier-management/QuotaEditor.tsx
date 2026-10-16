import {
  Box,
  Button,
  FormControl,
  FormErrorMessage,
  Grid,
  HStack,
  IconButton,
  Input,
  NumberInput,
  NumberInputField,
  Select,
  Text,
  Tooltip,
  VStack,
} from "@chakra-ui/react";
import { AddIcon, DeleteIcon, SmallCloseIcon } from "@chakra-ui/icons";
import { FiCalendar } from "react-icons/fi";
import { FORM_LABEL_TO_INPUT_PT } from "../common/FormFieldsRow";
import FieldHint from "../common/FieldHint";
import FieldLabel from "../common/FieldLabel";
import { formatModelTaskTypeLabel } from "../../config/constants";
import { FIELD_HINTS } from "../../config/fieldHints";
import type { TierFormQuota } from "../../types/tierManagement";
import { generateUUID } from "../../utils/uuid";
import { QUOTA_LIMIT_MAX, validateQuotaLimit } from "./tierFormValidation";

interface QuotaEditorProps {
  readonly quotas: TierFormQuota[];
  readonly onChange: (quotas: TierFormQuota[]) => void;
  readonly taskTypeNames: string[];
  readonly unitByTaskType: Record<string, string>;
  readonly onSchedule?: (quota: TierFormQuota) => void;
  readonly onRemove?: (quota: TierFormQuota) => void;
  readonly removingTaskType?: string | null;
  readonly isEditMode?: boolean;
  readonly mode?: "create" | "edit" | "view";
  readonly showErrors?: boolean;
}

function isUnitInvalid(quota: TierFormQuota): boolean {
  return !quota.unit.trim();
}

/**
 * Inline verdict for a quota row's limit. Delegates to the shared rule so the
 * form and `validateQuotas` (which gates submit) cannot drift apart.
 */
function limitError(quota: TierFormQuota): string | null {
  return validateQuotaLimit(quota.limit);
}

function showLimitError(quota: TierFormQuota, showErrors?: boolean): boolean {
  return (showErrors || !!quota.limit.trim()) && !!limitError(quota);
}

export function QuotaEditor({
  quotas,
  onChange,
  taskTypeNames,
  unitByTaskType,
  onSchedule,
  onRemove,
  removingTaskType,
  isEditMode,
  showErrors,
}: QuotaEditorProps) {
  const handleQuotaChange = (
    idx: number,
    field: keyof TierFormQuota,
    value: string,
  ) => {
    const updated = quotas.map((q, i) => {
      if (i !== idx) return q;
      if (field === "modelTaskType") {
        return {
          ...q,
          modelTaskType: value,
          unit: unitByTaskType[value] ?? "",
        };
      }
      return { ...q, [field]: value };
    });
    onChange(updated);
  };

  const addQuota = () => {
    onChange([
      ...quotas,
      {
        _key: generateUUID(),
        modelTaskType: "",
        unit: "",
        limit: "",
      },
    ]);
  };

  const removeQuota = (idx: number) =>
    onChange(quotas.filter((_, i) => i !== idx));

  // "Add Quota" only makes sense when there's more than one model task type
  // to choose from, and only while there's an unused type left to add.
  const canAddQuota =
    taskTypeNames.length > 1 && quotas.length < taskTypeNames.length;

  return (
    <VStack align="stretch" spacing={3}>
      <HStack justify="space-between">
        <Text fontSize="sm" fontWeight="semibold" color="ink.700">
          Quotas
        </Text>
        {!isEditMode && canAddQuota && (
          <Button
            size="xs"
            leftIcon={<AddIcon />}
            variant="outline"
            colorScheme="blue"
            onClick={addQuota}
          >
            Add Quota
          </Button>
        )}
      </HStack>

      <Box maxH="340px" overflowY="auto" pr={1}>
        <VStack align="stretch" spacing={3}>
          {quotas.map((quota, idx) => (
            <Box
              key={quota._key ?? `${quota.modelTaskType}-${idx}`}
              p={3}
              borderWidth="1px"
              borderRadius="md"
              borderColor="ink.200"
              bg="ink.50"
            >
              <HStack align="flex-start" spacing={3}>
                <Grid
                  templateColumns={{
                    base: "1fr",
                    sm: "minmax(0, 1.6fr) minmax(0, 1fr) minmax(0, 1fr)",
                  }}
                  gap={3}
                  flex={1}
                  minW={0}
                  alignItems="start"
                >
                  <FormControl isRequired isDisabled={isEditMode} minW={0}>
                    <FieldLabel formLabelProps={{ fontSize: "xs", mb: 1 }}>
                      Model Task Type
                    </FieldLabel>
                    <Select
                      size="sm"
                      value={quota.modelTaskType}
                      onChange={(e) =>
                        handleQuotaChange(idx, "modelTaskType", e.target.value)
                      }
                    >
                      <option value="" disabled>
                        Select model task type
                      </option>
                      {taskTypeNames
                        ?.filter((t) => {
                          const selectedElsewhere = quotas
                            .filter((_, i) => i !== idx)
                            .map((q) => q.modelTaskType);
                          return (
                            !selectedElsewhere.includes(t) ||
                            t === quota.modelTaskType
                          );
                        })
                        .map((t) => (
                          <option key={t} value={t}>
                            {formatModelTaskTypeLabel(t)}
                          </option>
                        ))}
                    </Select>
                  </FormControl>

                  <FormControl
                    isRequired
                    isInvalid={showErrors && isUnitInvalid(quota)}
                    isDisabled={isEditMode}
                    minW={0}
                  >
                    <FieldLabel formLabelProps={{ fontSize: "xs", mb: 1 }}>
                      Unit
                    </FieldLabel>
                    <Input
                      size="sm"
                      value={quota.unit}
                      isReadOnly
                      placeholder="-"
                      bg="ink.50"
                      cursor="default"
                    />
                    <FormErrorMessage fontSize="xs">
                      Unit is required.
                    </FormErrorMessage>
                    <FieldHint show={!(showErrors && isUnitInvalid(quota))}>
                      {FIELD_HINTS.tier.quotaUnit.helper}
                    </FieldHint>
                  </FormControl>

                  <FormControl
                    isRequired
                    isInvalid={showLimitError(quota, showErrors)}
                    isDisabled={isEditMode}
                    minW={0}
                  >
                    <FieldLabel formLabelProps={{ fontSize: "xs", mb: 1 }}>
                      Limit
                    </FieldLabel>
                    <NumberInput
                      size="sm"
                      min={0}
                      max={QUOTA_LIMIT_MAX}
                      step={1}
                      // An out-of-range value must survive blur so the inline
                      // error can name it; clamping would silently rewrite it.
                      clampValueOnBlur={false}
                      value={quota.limit}
                      onChange={(v) => handleQuotaChange(idx, "limit", v)}
                    >
                      <NumberInputField
                        placeholder={FIELD_HINTS.tier.quotaLimit.placeholder}
                      />
                    </NumberInput>
                    <FormErrorMessage fontSize="xs">
                      {limitError(quota)}
                    </FormErrorMessage>
                    <FieldHint show={!showLimitError(quota, showErrors)}>
                      {FIELD_HINTS.tier.quotaLimit.helper}
                    </FieldHint>
                  </FormControl>
                </Grid>

                {quota.isExisting && onSchedule && (
                  <Tooltip label="Schedule a change" placement="top" hasArrow>
                    <IconButton
                      aria-label="Schedule a change"
                      icon={<FiCalendar />}
                      size="sm"
                      variant="ghost"
                      colorScheme="blue"
                      onClick={() => onSchedule(quota)}
                      mt={FORM_LABEL_TO_INPUT_PT}
                    />
                  </Tooltip>
                )}

                {!isEditMode && quota.isExisting && onRemove && (
                  <Tooltip label="Remove quota" placement="top" hasArrow>
                    <IconButton
                      aria-label="Remove quota"
                      icon={<SmallCloseIcon />}
                      size="sm"
                      variant="ghost"
                      colorScheme="gray"
                      isLoading={removingTaskType === quota.modelTaskType}
                      isDisabled={
                        !!removingTaskType &&
                        removingTaskType !== quota.modelTaskType
                      }
                      onClick={() => onRemove(quota)}
                      mt={FORM_LABEL_TO_INPUT_PT}
                    />
                  </Tooltip>
                )}

                {!isEditMode && !quota.isExisting && quotas.length > 1 && (
                  <IconButton
                    aria-label="Remove quota"
                    icon={<DeleteIcon />}
                    size="sm"
                    variant="ghost"
                    colorScheme="red"
                    onClick={() => removeQuota(idx)}
                    mt={FORM_LABEL_TO_INPUT_PT}
                  />
                )}
              </HStack>
            </Box>
          ))}
        </VStack>
      </Box>
    </VStack>
  );
}
