// Create/Edit Service tab: single form shared between create and edit modes
// Field order & LLM vs non-LLM Service ID behavior
import {
  Badge,
  Box,
  Button,
  Checkbox,
  FormControl,
  FormErrorMessage,
  HStack,
  Input,
  IconButton,
  InputGroup,
  InputLeftElement,
  InputRightElement,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
  Portal,
  Select,
  SimpleGrid,
  Text,
  Textarea,
  VStack,
} from "@chakra-ui/react";
import { ChevronDownIcon, SearchIcon, ViewIcon, ViewOffIcon } from "@chakra-ui/icons";
import React, { useMemo, useState } from "react";
import { formatModelTaskTypeLabel, getTaskColorScheme } from "../../config/constants";
import { FIELD_HINTS } from "../../config/fieldHints";
import FieldLabel from "../common/FieldLabel";
import ReadOnlyField from "../common/ReadOnlyField";
import type { Service } from "../../services/servicesManagementService";
import type { ModelDetails } from "../../types/platform";
import type { Tier } from "../../types/tierManagement";
import { ServiceFormFields } from "./serviceFormFields";
import {
  INFRA_DESCRIPTION_MAX_LEN,
  INFRA_DESCRIPTION_MIN_LEN,
  PRICE_PER_UNIT_MAX,
  PRICE_LABEL,
  LLM_CACHED_INPUT_PRICE_LABEL,
  LLM_INPUT_PRICE_LABEL,
  LLM_OUTPUT_PRICE_LABEL,
  SERVICE_DESCRIPTION_MAX_LEN,
  SERVICE_DESCRIPTION_MIN_LEN,
  SERVICE_ID_MAX_LEN,
  SERVICE_NAME_MAX_LEN,
  sanitizeServiceId,
  sanitizeServiceName,
} from "./serviceFormValidation";

/** Billing unit-size presets shown as a dropdown. */
export const UNIT_SIZE_OPTIONS = ["1000", "1000000"] as const;

/** Currency reference list for the create form. */
export const CURRENCY_OPTIONS = ["INR"] as const;

interface ServiceFormTabProps {
  editingService: Service | null;
  formData: Partial<Service>;
  onInputChange: (field: keyof Service, value: string) => void;
  onTaskTypeChange: (taskType: string) => void;
  onModelNameChange: (modelId: string) => void;
  taskTypeNames: string[];
  isLoadingModels: boolean;
  filteredModelsForDropdown: ModelDetails[];
  unitType: string;
  pricePerUnit: string;
  pricePerUnitError?: string | null;
  onPricePerUnitChange: (value: string) => void;
  /** LLM only: pricePerUnit is then the input token price. */
  cachedInputPricePerUnit: string;
  cachedInputPricePerUnitError?: string | null;
  onCachedInputPricePerUnitChange: (value: string) => void;
  outputPricePerUnit: string;
  outputPricePerUnitError?: string | null;
  onOutputPricePerUnitChange: (value: string) => void;
  unitSize: string;
  onUnitSizeChange: (value: string) => void;
  currency: string;
  onCurrencyChange: (value: string) => void;
  selectedTiers: string[];
  onToggleTier: (tierId: string) => void;
  availableTiers: Tier[];
  isCreateFormModelSelected: boolean;
  isLlmTaskType: boolean;
  authToken: string;
  onAuthTokenChange: (value: string) => void;
  hasAuthToken: boolean;
  /** Backend's masked stand-in ("***") for an already-saved token, if any. */
  savedAuthTokenMask?: string;
  serviceIdError?: string | null;
  serviceIdLengthError?: string | null;
  serviceDescriptionError?: string | null;
  serviceNameError?: string | null;
  hardwareDescriptionError?: string | null;
  onSubmit: (e: React.FormEvent) => void;
  /** View reuses this form read-only. Create and edit stay the default. */
  mode?: "create" | "edit" | "view";
  formId?: string;
}

const formatSubmissionDateDisplay = (value?: string): string => {
  if (!value) return "—";
  // value is YYYY-MM-DD from the hook; show a readable date
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
};


function resolveFormMode(
  mode: "create" | "edit" | "view" | undefined,
  editingService: unknown,
): "create" | "edit" | "view" {
  if (mode) return mode;
  if (editingService) return "edit";
  return "create";
}

function modelNamePlaceholder(options: {
  isLoadingModels: boolean;
  hasTaskType: boolean;
}): string {
  if (options.isLoadingModels) return FIELD_HINTS.service.modelName.loading;
  if (!options.hasTaskType) return FIELD_HINTS.service.modelName.needTaskType;
  return FIELD_HINTS.service.modelName.placeholder;
}

function authTokenFieldCopy(options: {
  isEditing: boolean;
  hasAuthToken: boolean;
}): { tip: string; helper?: string } {
  if (!options.isEditing) {
    return { tip: FIELD_HINTS.service.authToken.tip };
  }
  if (options.hasAuthToken) {
    return {
      tip: FIELD_HINTS.service.authToken.editTip,
      helper: FIELD_HINTS.service.authToken.editHelper,
    };
  }
  return { tip: FIELD_HINTS.service.authToken.editEmptyTip };
}

const ServiceFormTab: React.FC<Readonly<ServiceFormTabProps>> = ({
  editingService,
  formData,
  onInputChange,
  onTaskTypeChange,
  onModelNameChange,
  taskTypeNames,
  isLoadingModels,
  filteredModelsForDropdown,
  unitType,
  pricePerUnit,
  pricePerUnitError,
  onPricePerUnitChange,
  cachedInputPricePerUnit,
  cachedInputPricePerUnitError,
  onCachedInputPricePerUnitChange,
  outputPricePerUnit,
  outputPricePerUnitError,
  onOutputPricePerUnitChange,
  unitSize,
  onUnitSizeChange,
  currency,
  onCurrencyChange,
  selectedTiers,
  onToggleTier,
  availableTiers,
  isCreateFormModelSelected,
  isLlmTaskType,
  authToken,
  onAuthTokenChange,
  hasAuthToken,
  savedAuthTokenMask = "",
  serviceIdError,
  serviceIdLengthError,
  serviceDescriptionError,
  serviceNameError,
  hardwareDescriptionError,
  onSubmit,
  formId,
  mode,
}) => {
  const formMode = resolveFormMode(mode, editingService);
  const isView = formMode === "view";
  const unitSizeSelectOptions = useMemo(() => {
    const opts: string[] = [...UNIT_SIZE_OPTIONS];
    if (unitSize && !opts.includes(unitSize)) {
      opts.push(unitSize);
    }
    return opts;
  }, [unitSize]);

  const [blurred, setBlurred] = useState<Record<string, boolean>>({});
  const markBlurred = (field: string) =>
    setBlurred((prev) => (prev[field] ? prev : { ...prev, [field]: true }));
  const afterBlur = (field: string, error?: string | null): string | null => {
    if (!blurred[field]) return null;
    return error ?? null;
  };

  const nameError = afterBlur("name", serviceNameError);
  const descriptionError = afterBlur("serviceDescription", serviceDescriptionError);
  const infraError = afterBlur("hardwareDescription", hardwareDescriptionError);

  // A price shows its error once it holds anything; an empty one waits for a blur.
  const priceFieldError = (field: string, value: string, error?: string | null) => {
    if (value.trim()) return error ?? null;
    return afterBlur(field, error);
  };

  const renderPriceField = (
    field: string,
    label: string,
    value: string,
    error: string | null | undefined,
    onChange: (value: string) => void,
    helper: string,
    placeholder: string = FIELD_HINTS.service.price.placeholder,
    tip?: string,
  ) => {
    if (isView) {
      return <ReadOnlyField label={label}>{value || "—"}</ReadOnlyField>;
    }
    const shownError = priceFieldError(field, value, error);
    return (
      <FormControl isRequired isInvalid={!!shownError}>
        <FieldLabel hint={tip}>{label}</FieldLabel>
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onBlur={() => markBlurred(field)}
          placeholder={placeholder}
          type="number"
          min={0}
          max={PRICE_PER_UNIT_MAX}
          bg="white"
        />
        {shownError ? <FormErrorMessage>{shownError}</FormErrorMessage> : null}
      </FormControl>
    );
  };
  // Duplicate clash wins. Length shows once the field holds anything — the
  // prefill fills it without a blur — but an empty field still waits for one.
  const idError =
    serviceIdError ??
    (formData.serviceId?.trim()
      ? (serviceIdLengthError ?? null)
      : afterBlur("serviceId", serviceIdLengthError));

  const [tierSearch, setTierSearch] = useState("");

  const [showAuthToken, setShowAuthToken] = useState(false);
  const isShowingSavedAuthMask =
    !!savedAuthTokenMask && authToken === savedAuthTokenMask;
  const handleAuthTokenChange = (next: string) => {
    if (!isShowingSavedAuthMask) {
      onAuthTokenChange(next);
      return;
    }
    if (next.includes(savedAuthTokenMask)) {
      onAuthTokenChange(next.split(savedAuthTokenMask).join(""));
      return;
    }
    const isPartialMask =
      next === "" ||
      savedAuthTokenMask.startsWith(next) ||
      savedAuthTokenMask.endsWith(next);
    onAuthTokenChange(isPartialMask ? "" : next);
  };

  /**
   * Names for the service's own tier ids, which `availableTiers` need not
   * contain — it is narrowed by status and by task type, so a mapped tier can
   * be missing from it without being invalid. `tierIds` and `tierNames` come
   * back positionally aligned.
   */
  const mappedTierNameById = useMemo(() => {
    const byId = new Map<string, string>();
    const ids = editingService?.tierIds ?? [];
    const names = editingService?.tierNames ?? [];
    ids.forEach((id, i) => {
      if (id) byId.set(id, names[i] || id);
    });
    return byId;
  }, [editingService]);

  const resolveTierName = (id: string) =>
    availableTiers.find((t) => t.id === id)?.name ??
    mappedTierNameById.get(id) ??
    id;

  const selectedTierNames = useMemo(
    () => selectedTiers.map(resolveTierName),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [selectedTiers, availableTiers, mappedTierNameById],
  );

  /**
   * Selected tiers the picker does not list. Shown and kept selected rather
   * than dropped: re-submitting the unchanged set preserves the mapping and
   * skips server-side revalidation, so editing an unrelated field does not
   * rewrite it.
   */
  const unlistedSelectedTiers = useMemo(
    () =>
      selectedTiers
        .filter((id) => !availableTiers.some((t) => t.id === id))
        .map((id) => ({ id, name: resolveTierName(id) })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [selectedTiers, availableTiers, mappedTierNameById],
  );

  const filteredTiers = useMemo(() => {
    const q = tierSearch.trim().toLowerCase();
    if (!q) return availableTiers;
    return availableTiers.filter((tier) =>
      (tier.name || "").toLowerCase().includes(q),
    );
  }, [availableTiers, tierSearch]);

  const showServiceName = !isLlmTaskType;

  // Field groups are separated by spacing alone — no section headers.
  const sections = (
    <ServiceFormFields
      isView={isView}
      editingService={editingService}
      formData={formData}
      onInputChange={onInputChange}
      onTaskTypeChange={onTaskTypeChange}
      onModelNameChange={onModelNameChange}
      taskTypeNames={taskTypeNames}
      isLoadingModels={isLoadingModels}
      filteredModelsForDropdown={filteredModelsForDropdown}
      unitType={unitType}
      pricePerUnit={pricePerUnit}
      pricePerUnitError={pricePerUnitError}
      onPricePerUnitChange={onPricePerUnitChange}
      cachedInputPricePerUnit={cachedInputPricePerUnit}
      cachedInputPricePerUnitError={cachedInputPricePerUnitError}
      onCachedInputPricePerUnitChange={onCachedInputPricePerUnitChange}
      outputPricePerUnit={outputPricePerUnit}
      outputPricePerUnitError={outputPricePerUnitError}
      onOutputPricePerUnitChange={onOutputPricePerUnitChange}
      unitSize={unitSize}
      onUnitSizeChange={onUnitSizeChange}
      unitSizeSelectOptions={unitSizeSelectOptions}
      currency={currency}
      onCurrencyChange={onCurrencyChange}
      selectedTiers={selectedTiers}
      selectedTierNames={selectedTierNames}
      onToggleTier={onToggleTier}
      availableTiers={availableTiers}
      filteredTiers={filteredTiers}
      unlistedSelectedTiers={unlistedSelectedTiers}
      tierSearch={tierSearch}
      onTierSearchChange={setTierSearch}
      isCreateFormModelSelected={isCreateFormModelSelected}
      isLlmTaskType={isLlmTaskType}
      showServiceName={showServiceName}
      authToken={authToken}
      handleAuthTokenChange={handleAuthTokenChange}
      hasAuthToken={hasAuthToken}
      isShowingSavedAuthMask={isShowingSavedAuthMask}
      showAuthToken={showAuthToken}
      onToggleShowAuthToken={() => setShowAuthToken((prev) => !prev)}
      nameError={nameError}
      descriptionError={descriptionError}
      infraError={infraError}
      idError={idError}
      markBlurred={markBlurred}
      formatSubmissionDateDisplay={formatSubmissionDateDisplay}
      modelNamePlaceholder={modelNamePlaceholder}
      authTokenFieldCopy={authTokenFieldCopy}
      renderPriceField={renderPriceField}
    />
  );
  if (isView) {
    return (
      <Box borderTopWidth="1px" borderColor="ink.200" mt={1} pt={5}>
        {sections}
      </Box>
    );
  }

  return (
    <form id={formId} onSubmit={onSubmit}>
      {sections}
    </form>
  );
};

export default ServiceFormTab;
