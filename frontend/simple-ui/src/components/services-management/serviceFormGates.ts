import type { Service } from "../../services/servicesManagementService";
import {
  LLM_CACHED_INPUT_PRICE_LABEL,
  LLM_INPUT_PRICE_LABEL,
  LLM_OUTPUT_PRICE_LABEL,
  SERVICE_NAME_MAX_LEN,
  validateHardwareDescription,
  validatePricePerUnit,
  validateServiceDescription,
  validateServiceIdLength,
  validateServiceName,
} from "./serviceFormValidation";

type FormGateInput = {
  formData: Partial<Service>;
  editingService: Service | null;
  isLlmTaskType: boolean;
  pricePerUnit: string;
  cachedInputPricePerUnit: string;
  outputPricePerUnit: string;
  unitSize: string;
  currency: string;
  selectedTiers: string[];
  existingServiceIds: Set<string>;
  shouldValidateHardware: boolean;
};

export type ServiceFormGates = {
  isUnitSizeValid: boolean;
  pricePerUnitError: string | null;
  cachedInputPricePerUnitError: string | null;
  outputPricePerUnitError: string | null;
  serviceIdExists: boolean;
  serviceIdError: string | null;
  serviceDescriptionError: string | null;
  serviceNameError: string | null;
  hardwareDescriptionError: string | null;
  serviceIdLengthError: string | null;
  canCreateService: boolean;
  isCreateFormModelSelected: boolean;
};

function serviceIdLengthGate(
  isCreateMode: boolean,
  isLlmTaskType: boolean,
  serviceId: string | undefined,
): string | null {
  if (!isCreateMode) return null;
  const lengthError = validateServiceIdLength(serviceId);
  if (lengthError) return lengthError;
  const trimmed = (serviceId || "").trim();
  if (isLlmTaskType && trimmed.length > SERVICE_NAME_MAX_LEN) {
    return `Service ID must not exceed ${SERVICE_NAME_MAX_LEN} characters, because it is also used as the Service Name.`;
  }
  return null;
}

export function computeServiceFormGates(input: FormGateInput): ServiceFormGates {
  const isCreateMode = !input.editingService;
  const isUnitSizeValid =
    /^\d+$/.test(input.unitSize.trim()) && Number(input.unitSize) > 0;

  const pricePerUnitError = validatePricePerUnit(
    input.pricePerUnit,
    input.isLlmTaskType ? LLM_INPUT_PRICE_LABEL : undefined,
  );
  const cachedInputPricePerUnitError = input.isLlmTaskType
    ? validatePricePerUnit(
        input.cachedInputPricePerUnit,
        LLM_CACHED_INPUT_PRICE_LABEL,
      )
    : null;
  const outputPricePerUnitError = input.isLlmTaskType
    ? validatePricePerUnit(input.outputPricePerUnit, LLM_OUTPUT_PRICE_LABEL)
    : null;

  const trimmedServiceId = input.formData.serviceId?.trim() || "";
  const serviceIdExists =
    isCreateMode &&
    Boolean(trimmedServiceId) &&
    input.existingServiceIds.has(trimmedServiceId);
  const serviceIdError = serviceIdExists ? "Service Id already exists" : null;

  const serviceDescriptionError = isCreateMode
    ? validateServiceDescription(input.formData.serviceDescription)
    : null;
  const serviceNameError =
    isCreateMode && !input.isLlmTaskType
      ? validateServiceName(input.formData.name)
      : null;
  const hardwareDescriptionError = input.shouldValidateHardware
    ? validateHardwareDescription(input.formData.hardwareDescription)
    : null;
  const serviceIdLengthError = serviceIdLengthGate(
    isCreateMode,
    input.isLlmTaskType,
    input.formData.serviceId,
  );

  const meetsCreateFieldRules =
    !serviceDescriptionError &&
    !serviceNameError &&
    !hardwareDescriptionError &&
    !serviceIdLengthError;

  const hasRequiredServiceIdentity = input.isLlmTaskType
    ? Boolean(trimmedServiceId)
    : Boolean(input.formData.name?.trim()) && Boolean(trimmedServiceId);

  const canCreateService =
    hasRequiredServiceIdentity &&
    !serviceIdExists &&
    meetsCreateFieldRules &&
    Boolean(input.formData.modelId?.trim()) &&
    Boolean(input.formData.endpoint?.trim()) &&
    Boolean(input.formData.task_type?.trim()) &&
    !pricePerUnitError &&
    !cachedInputPricePerUnitError &&
    !outputPricePerUnitError &&
    Boolean(input.currency.trim()) &&
    isUnitSizeValid &&
    input.selectedTiers.length > 0;

  return {
    isUnitSizeValid,
    pricePerUnitError,
    cachedInputPricePerUnitError,
    outputPricePerUnitError,
    serviceIdExists,
    serviceIdError,
    serviceDescriptionError,
    serviceNameError,
    hardwareDescriptionError,
    serviceIdLengthError,
    canCreateService,
    isCreateFormModelSelected: Boolean(input.formData.modelId?.trim()),
  };
}

export function hasActiveClientServiceFilters(options: {
  filterStatus: string;
  filterTaskType: string;
  filterTier: string;
  searchQuery: string;
  showTaskTypeAllOption: boolean;
  allTierValue: string;
}): boolean {
  if (options.filterStatus !== "") return true;
  if (options.showTaskTypeAllOption && options.filterTaskType !== "") return true;
  if (options.filterTier !== options.allTierValue) return true;
  return options.searchQuery.trim() !== "";
}

export function hasActiveServerServiceFilters(
  serverFilters: Record<string, string>,
  taskFilterColumnId: string | undefined,
  taskTypeNames: string[],
): boolean {
  for (const [id, value] of Object.entries(serverFilters)) {
    const trimmed = value.trim();
    if (!trimmed) continue;
    if (
      id === taskFilterColumnId &&
      taskTypeNames.length === 1 &&
      trimmed === taskTypeNames[0]
    ) {
      continue;
    }
    return true;
  }
  return false;
}
