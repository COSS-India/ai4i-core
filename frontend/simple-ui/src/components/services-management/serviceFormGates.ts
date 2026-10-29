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

type FormGateInput = Readonly<{
  formData: Partial<Service>;
  editingService: Service | null;
  isLlmTaskType: boolean;
  pricePerUnit: string;
  cachedInputPricePerUnit: string;
  outputPricePerUnit: string;
  unitSize: string;
  currency: string;
  selectedTiers: readonly string[];
  existingServiceIds: ReadonlySet<string>;
  shouldValidateHardware: boolean;
}>;

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
  if (!isLlmTaskType) return null;
  if (trimmed.length <= SERVICE_NAME_MAX_LEN) return null;
  return `Service ID must not exceed ${SERVICE_NAME_MAX_LEN} characters, because it is also used as the Service Name.`;
}

function isUnitSizeValidValue(unitSize: string): boolean {
  if (!/^\d+$/.test(unitSize.trim())) return false;
  return Number(unitSize) > 0;
}

function computePriceErrors(input: FormGateInput): {
  pricePerUnitError: string | null;
  cachedInputPricePerUnitError: string | null;
  outputPricePerUnitError: string | null;
} {
  const pricePerUnitError = validatePricePerUnit(
    input.pricePerUnit,
    input.isLlmTaskType ? LLM_INPUT_PRICE_LABEL : undefined,
  );
  if (!input.isLlmTaskType) {
    return {
      pricePerUnitError,
      cachedInputPricePerUnitError: null,
      outputPricePerUnitError: null,
    };
  }
  return {
    pricePerUnitError,
    cachedInputPricePerUnitError: validatePricePerUnit(
      input.cachedInputPricePerUnit,
      LLM_CACHED_INPUT_PRICE_LABEL,
    ),
    outputPricePerUnitError: validatePricePerUnit(
      input.outputPricePerUnit,
      LLM_OUTPUT_PRICE_LABEL,
    ),
  };
}

function computeFieldErrors(
  input: FormGateInput,
  isCreateMode: boolean,
  trimmedServiceId: string,
): {
  serviceIdExists: boolean;
  serviceIdError: string | null;
  serviceDescriptionError: string | null;
  serviceNameError: string | null;
  hardwareDescriptionError: string | null;
  serviceIdLengthError: string | null;
} {
  const serviceIdExists =
    isCreateMode &&
    Boolean(trimmedServiceId) &&
    input.existingServiceIds.has(trimmedServiceId);

  let serviceDescriptionError: string | null = null;
  let serviceNameError: string | null = null;
  if (isCreateMode) {
    serviceDescriptionError = validateServiceDescription(
      input.formData.serviceDescription,
    );
    if (!input.isLlmTaskType) {
      serviceNameError = validateServiceName(input.formData.name);
    }
  }

  let hardwareDescriptionError: string | null = null;
  if (input.shouldValidateHardware) {
    hardwareDescriptionError = validateHardwareDescription(
      input.formData.hardwareDescription,
    );
  }

  return {
    serviceIdExists,
    serviceIdError: serviceIdExists ? "Service Id already exists" : null,
    serviceDescriptionError,
    serviceNameError,
    hardwareDescriptionError,
    serviceIdLengthError: serviceIdLengthGate(
      isCreateMode,
      input.isLlmTaskType,
      input.formData.serviceId,
    ),
  };
}

function hasRequiredServiceIdentity(
  isLlmTaskType: boolean,
  trimmedServiceId: string,
  name: string | undefined,
): boolean {
  if (isLlmTaskType) return Boolean(trimmedServiceId);
  return Boolean(name?.trim()) && Boolean(trimmedServiceId);
}

function computeCanCreateService(options: Readonly<{
  hasRequiredServiceIdentity: boolean;
  serviceIdExists: boolean;
  meetsCreateFieldRules: boolean;
  formData: Partial<Service>;
  pricePerUnitError: string | null;
  cachedInputPricePerUnitError: string | null;
  outputPricePerUnitError: string | null;
  currency: string;
  isUnitSizeValid: boolean;
  selectedTiers: readonly string[];
}>): boolean {
  if (!options.hasRequiredServiceIdentity) return false;
  if (options.serviceIdExists) return false;
  if (!options.meetsCreateFieldRules) return false;
  if (!options.formData.modelId?.trim()) return false;
  if (!options.formData.endpoint?.trim()) return false;
  if (!options.formData.task_type?.trim()) return false;
  if (options.pricePerUnitError) return false;
  if (options.cachedInputPricePerUnitError) return false;
  if (options.outputPricePerUnitError) return false;
  if (!options.currency.trim()) return false;
  if (!options.isUnitSizeValid) return false;
  return options.selectedTiers.length > 0;
}

export function computeServiceFormGates(input: FormGateInput): ServiceFormGates {
  const isCreateMode = !input.editingService;
  const isUnitSizeValid = isUnitSizeValidValue(input.unitSize);
  const priceErrors = computePriceErrors(input);
  const trimmedServiceId = input.formData.serviceId?.trim() || "";
  const fieldErrors = computeFieldErrors(input, isCreateMode, trimmedServiceId);

  const meetsCreateFieldRules =
    !fieldErrors.serviceDescriptionError &&
    !fieldErrors.serviceNameError &&
    !fieldErrors.hardwareDescriptionError &&
    !fieldErrors.serviceIdLengthError;

  const canCreateService = computeCanCreateService({
    hasRequiredServiceIdentity: hasRequiredServiceIdentity(
      input.isLlmTaskType,
      trimmedServiceId,
      input.formData.name,
    ),
    serviceIdExists: fieldErrors.serviceIdExists,
    meetsCreateFieldRules,
    formData: input.formData,
    pricePerUnitError: priceErrors.pricePerUnitError,
    cachedInputPricePerUnitError: priceErrors.cachedInputPricePerUnitError,
    outputPricePerUnitError: priceErrors.outputPricePerUnitError,
    currency: input.currency,
    isUnitSizeValid,
    selectedTiers: input.selectedTiers,
  });

  return {
    isUnitSizeValid,
    ...priceErrors,
    ...fieldErrors,
    canCreateService,
    isCreateFormModelSelected: Boolean(input.formData.modelId?.trim()),
  };
}

export function hasActiveClientServiceFilters(options: {
  filterStatus: string;
  filterTaskType: string;
  searchQuery?: string;
  showTaskTypeAllOption: boolean;
}): boolean {
  if (options.filterStatus !== "") return true;
  if (options.showTaskTypeAllOption && options.filterTaskType !== "") {
    return true;
  }
  return (options.searchQuery ?? "").trim() !== "";
}

export function hasActiveServerServiceFilters(
  serverFilters: Record<string, string>,
  taskFilterColumnId: string | undefined,
  taskTypeNames: string[],
): boolean {
  for (const [id, value] of Object.entries(serverFilters)) {
    const trimmed = value.trim();
    if (!trimmed) continue;
    const lockedSingleTask =
      id === taskFilterColumnId &&
      taskTypeNames.length === 1 &&
      trimmed === taskTypeNames[0];
    if (lockedSingleTask) continue;
    return true;
  }
  return false;
}
