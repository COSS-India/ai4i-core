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
import FieldHint from "../common/FieldHint";
import FieldLabel from "../common/FieldLabel";
import ReadOnlyField from "../common/ReadOnlyField";
import type { Service } from "../../services/servicesManagementService";
import type { ModelDetails } from "../../types/platform";
import type { Tier } from "../../types/tierManagement";
import {
  INFRA_DESCRIPTION_MAX_LEN,
  INFRA_DESCRIPTION_MIN_LEN,
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

const CURRENCY_OPTIONS = ["INR"] as const;

export type ServiceFormFieldsProps = {
  isView: boolean;
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
  cachedInputPricePerUnit: string;
  cachedInputPricePerUnitError?: string | null;
  onCachedInputPricePerUnitChange: (value: string) => void;
  outputPricePerUnit: string;
  outputPricePerUnitError?: string | null;
  onOutputPricePerUnitChange: (value: string) => void;
  unitSize: string;
  onUnitSizeChange: (value: string) => void;
  unitSizeSelectOptions: string[];
  currency: string;
  onCurrencyChange: (value: string) => void;
  selectedTiers: string[];
  selectedTierNames: string[];
  onToggleTier: (tierId: string) => void;
  availableTiers: Tier[];
  filteredTiers: Tier[];
  unlistedSelectedTiers: { id: string; name: string }[];
  tierSearch: string;
  onTierSearchChange: (value: string) => void;
  isCreateFormModelSelected: boolean;
  isLlmTaskType: boolean;
  showServiceName: boolean;
  authToken: string;
  handleAuthTokenChange: (next: string) => void;
  hasAuthToken: boolean;
  isShowingSavedAuthMask: boolean;
  showAuthToken: boolean;
  onToggleShowAuthToken: () => void;
  nameError: string | null;
  descriptionError: string | null;
  infraError: string | null;
  idError: string | null;
  markBlurred: (field: string) => void;
  formatSubmissionDateDisplay: (value?: string) => string;
  modelNamePlaceholder: (options: {
    isLoadingModels: boolean;
    hasTaskType: boolean;
  }) => string;
  authTokenFieldCopy: (options: {
    isEditing: boolean;
    hasAuthToken: boolean;
  }) => { tip: string; helper?: string };
  renderPriceField: (
    field: string,
    label: string,
    value: string,
    error: string | null | undefined,
    onChange: (value: string) => void,
    helper: string,
    placeholder?: string,
    tip?: string,
  ) => React.ReactNode;
};

type ModelSectionProps = Readonly<
  Pick<
    ServiceFormFieldsProps,
    | "isView"
    | "editingService"
    | "formData"
    | "onTaskTypeChange"
    | "onModelNameChange"
    | "taskTypeNames"
    | "isLoadingModels"
    | "filteredModelsForDropdown"
    | "isCreateFormModelSelected"
    | "formatSubmissionDateDisplay"
    | "modelNamePlaceholder"
  >
>;

type IdentitySectionProps = Readonly<
  Pick<
    ServiceFormFieldsProps,
    | "isView"
    | "editingService"
    | "formData"
    | "onInputChange"
    | "isLlmTaskType"
    | "showServiceName"
    | "nameError"
    | "descriptionError"
    | "idError"
    | "markBlurred"
  >
>;

type ConnectionSectionProps = Readonly<
  Pick<
    ServiceFormFieldsProps,
    | "isView"
    | "editingService"
    | "formData"
    | "onInputChange"
    | "isLlmTaskType"
    | "authToken"
    | "handleAuthTokenChange"
    | "hasAuthToken"
    | "isShowingSavedAuthMask"
    | "showAuthToken"
    | "onToggleShowAuthToken"
    | "infraError"
    | "markBlurred"
    | "authTokenFieldCopy"
  >
>;

type BillingSectionProps = Readonly<
  Pick<
    ServiceFormFieldsProps,
    | "isView"
    | "formData"
    | "unitType"
    | "pricePerUnit"
    | "pricePerUnitError"
    | "onPricePerUnitChange"
    | "cachedInputPricePerUnit"
    | "cachedInputPricePerUnitError"
    | "onCachedInputPricePerUnitChange"
    | "outputPricePerUnit"
    | "outputPricePerUnitError"
    | "onOutputPricePerUnitChange"
    | "unitSize"
    | "onUnitSizeChange"
    | "unitSizeSelectOptions"
    | "currency"
    | "onCurrencyChange"
    | "selectedTiers"
    | "selectedTierNames"
    | "onToggleTier"
    | "availableTiers"
    | "filteredTiers"
    | "unlistedSelectedTiers"
    | "tierSearch"
    | "onTierSearchChange"
    | "isLlmTaskType"
    | "renderPriceField"
  >
>;

function TaskTypeField({
  isView,
  editingService,
  formData,
  onTaskTypeChange,
  taskTypeNames,
}: Readonly<
  Pick<
    ModelSectionProps,
    "isView" | "editingService" | "formData" | "onTaskTypeChange" | "taskTypeNames"
  >
>): React.ReactElement {
  if (isView) {
    return (
      <ReadOnlyField label="Task Type">
        <Badge
          colorScheme={getTaskColorScheme(formData.task_type)}
          fontSize="sm"
          px={2}
          py={0.5}
        >
          {formData.task_type
            ? formatModelTaskTypeLabel(formData.task_type)
            : "N/A"}
        </Badge>
      </ReadOnlyField>
    );
  }
  return (
    <FormControl isRequired>
      <FieldLabel hint={FIELD_HINTS.service.taskType.tip}>Task Type</FieldLabel>
      {editingService ? (
        <Input
          value={formatModelTaskTypeLabel(formData.task_type || "")}
          isReadOnly
          bg="ink.50"
        />
      ) : (
        <Select
          value={formData.task_type || ""}
          onChange={(e) => onTaskTypeChange(e.target.value)}
          placeholder={FIELD_HINTS.service.taskType.placeholder}
          bg="white"
        >
          {taskTypeNames?.map((t) => (
            <option key={t} value={t}>
              {formatModelTaskTypeLabel(t)}
            </option>
          ))}
        </Select>
      )}
    </FormControl>
  );
}

function ModelNameField({
  isView,
  editingService,
  formData,
  onModelNameChange,
  isLoadingModels,
  filteredModelsForDropdown,
  modelNamePlaceholder,
}: Readonly<
  Pick<
    ModelSectionProps,
    | "isView"
    | "editingService"
    | "formData"
    | "onModelNameChange"
    | "isLoadingModels"
    | "filteredModelsForDropdown"
    | "modelNamePlaceholder"
  >
>): React.ReactElement {
  const [query, setQuery] = useState("");
  const selectedId = formData.modelId || "";
  const selected = filteredModelsForDropdown.find(
    (model) => (model.modelId || model.model_id) === selectedId,
  );
  const selectedLabel =
    selected?.name || formData.modelName || selectedId || modelNamePlaceholder({
      isLoadingModels,
      hasTaskType: Boolean(formData.task_type),
    });
  const q = query.trim().toLowerCase();
  const visibleModels = useMemo(
    () =>
      q
        ? filteredModelsForDropdown.filter((model) => {
            const name = (model.name || model.modelId || model.model_id || "").toLowerCase();
            return name.includes(q);
          })
        : filteredModelsForDropdown,
    [filteredModelsForDropdown, q],
  );

  if (isView) {
    return (
      <ReadOnlyField label="Model Name">
        {formData.modelName || formData.modelId || "—"}
      </ReadOnlyField>
    );
  }
  return (
    <FormControl isRequired>
      <FieldLabel hint={FIELD_HINTS.service.modelName.tip}>Model Name</FieldLabel>
      {editingService ? (
        <Input
          value={formData.modelName || formData.modelId || ""}
          isReadOnly
          bg="ink.50"
        />
      ) : (
        <Menu matchWidth onClose={() => setQuery("")}>
          <MenuButton
            as={Button}
            type="button"
            rightIcon={<ChevronDownIcon />}
            w="full"
            textAlign="left"
            fontWeight="normal"
            variant="outline"
            bg="white"
            justifyContent="space-between"
            isDisabled={isLoadingModels || !formData.task_type}
            aria-label="Model Name"
          >
            <Text as="span" isTruncated display="block" minW={0} color={selectedId ? "inherit" : "ink.500"}>
              {selectedLabel}
            </Text>
          </MenuButton>
          <Portal>
            <MenuList maxH="320px" overflow="hidden" p={0} zIndex={1500}>
              <Box px={3} py={2} borderBottomWidth="1px" borderColor="ink.100">
                <InputGroup size="sm">
                  <InputLeftElement pointerEvents="none">
                    <SearchIcon color="ink.400" />
                  </InputLeftElement>
                  <Input
                    placeholder="Search models..."
                    aria-label="Search models"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                    onKeyDown={(e) => {
                      if (e.key.length === 1 || e.key === "Backspace" || e.key === "Delete" || e.key === " ") {
                        e.stopPropagation();
                      }
                    }}
                    bg="white"
                  />
                </InputGroup>
              </Box>
              <Box maxH="240px" overflowY="auto" py={1} role="listbox" aria-label="Models">
                {visibleModels.length === 0 ? (
                  <Text px={3} py={2} fontSize="sm" color="ink.500">
                    {filteredModelsForDropdown.length === 0
                      ? "No models available"
                      : "No models match your search"}
                  </Text>
                ) : (
                  visibleModels.map((model) => {
                    const id = model.modelId || model.model_id || "";
                    const name = model.name || id;
                    return (
                      <MenuItem
                        key={id}
                        onClick={() => onModelNameChange(id)}
                        fontWeight={id === selectedId ? "semibold" : "normal"}
                      >
                        {name}
                      </MenuItem>
                    );
                  })
                )}
              </Box>
            </MenuList>
          </Portal>
        </Menu>
      )}
    </FormControl>
  );
}

function ServiceFormModelSection({
  isView,
  editingService,
  formData,
  onTaskTypeChange,
  onModelNameChange,
  taskTypeNames,
  isLoadingModels,
  filteredModelsForDropdown,
  isCreateFormModelSelected,
  formatSubmissionDateDisplay,
  modelNamePlaceholder,
}: ModelSectionProps): React.ReactElement {
  const submissionDate = formatSubmissionDateDisplay(formData.modelSubmissionDate);
  return (
    <VStack align="stretch" spacing={4}>
      <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
        <TaskTypeField
          isView={isView}
          editingService={editingService}
          formData={formData}
          onTaskTypeChange={onTaskTypeChange}
          taskTypeNames={taskTypeNames}
        />
        <ModelNameField
          isView={isView}
          editingService={editingService}
          formData={formData}
          onModelNameChange={onModelNameChange}
          isLoadingModels={isLoadingModels}
          filteredModelsForDropdown={filteredModelsForDropdown}
          modelNamePlaceholder={modelNamePlaceholder}
        />
      </SimpleGrid>

      <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
        {isView ? (
          <ReadOnlyField label="Model ID">{formData.modelId || "—"}</ReadOnlyField>
        ) : (
          <FormControl>
            <FieldLabel>Model ID</FieldLabel>
            <Text
              fontSize="sm"
              color={isCreateFormModelSelected ? "ink.800" : "ink.500"}
            >
              {formData.modelId || FIELD_HINTS.service.modelId.empty}
            </Text>
          </FormControl>
        )}
        {isView ? (
          <ReadOnlyField label="Model Submission Date">
            {submissionDate}
          </ReadOnlyField>
        ) : (
          <FormControl>
            <FieldLabel>Model Submission Date</FieldLabel>
            <Text
              fontSize="sm"
              color={formData.modelSubmissionDate ? "ink.800" : "ink.500"}
            >
              {isCreateFormModelSelected
                ? submissionDate
                : FIELD_HINTS.service.modelId.empty}
            </Text>
          </FormControl>
        )}
      </SimpleGrid>
    </VStack>
  );
}

function ServiceNameField({
  isView,
  editingService,
  formData,
  onInputChange,
  nameError,
  markBlurred,
}: Readonly<
  Pick<
    IdentitySectionProps,
    | "isView"
    | "editingService"
    | "formData"
    | "onInputChange"
    | "nameError"
    | "markBlurred"
  >
>): React.ReactElement | null {
  if (isView) {
    return <ReadOnlyField label="Service Name">{formData.name || "—"}</ReadOnlyField>;
  }
  return (
    <FormControl isRequired isInvalid={!!nameError}>
      <FieldLabel hint={FIELD_HINTS.service.name.tip}>Service Name</FieldLabel>
      <Input
        value={formData.name || ""}
        onBlur={() => markBlurred("name")}
        onChange={(e) =>
          onInputChange("name", sanitizeServiceName(e.target.value))
        }
        placeholder={FIELD_HINTS.service.name.placeholder}
        bg={editingService ? "ink.50" : "white"}
        isReadOnly={!!editingService}
        maxLength={SERVICE_NAME_MAX_LEN}
      />
      {nameError ? (
        <FormErrorMessage>{nameError}</FormErrorMessage>
      ) : (
        <FieldHint show={!editingService}>
          {FIELD_HINTS.service.name.helper}
        </FieldHint>
      )}
    </FormControl>
  );
}

function ServiceIdField({
  isView,
  editingService,
  formData,
  onInputChange,
  isLlmTaskType,
  idError,
  markBlurred,
}: Readonly<
  Pick<
    IdentitySectionProps,
    | "isView"
    | "editingService"
    | "formData"
    | "onInputChange"
    | "isLlmTaskType"
    | "idError"
    | "markBlurred"
  >
>): React.ReactElement {
  if (isView) {
    return <ReadOnlyField label="Service ID">{formData.serviceId || "—"}</ReadOnlyField>;
  }
  const serviceIdTip = isLlmTaskType
    ? FIELD_HINTS.service.serviceId.llmTip
    : FIELD_HINTS.service.serviceId.tip;
  return (
    <FormControl isRequired isInvalid={!!idError}>
      <FieldLabel hint={serviceIdTip}>Service ID</FieldLabel>
      <Input
        value={formData.serviceId || ""}
        onChange={(e) =>
          onInputChange(
            "serviceId",
            sanitizeServiceId(e.target.value, isLlmTaskType),
          )
        }
        onBlur={() => markBlurred("serviceId")}
        placeholder={
          formData.modelName
            ? `${formData.modelName}/…`
            : FIELD_HINTS.service.serviceId.placeholder
        }
        bg={editingService ? "ink.50" : "white"}
        isReadOnly={!!editingService}
        maxLength={SERVICE_ID_MAX_LEN}
      />
      {idError ? <FormErrorMessage>{idError}</FormErrorMessage> : null}
    </FormControl>
  );
}

function ServiceDescriptionField({
  isView,
  editingService,
  formData,
  onInputChange,
  descriptionError,
  markBlurred,
}: Readonly<
  Pick<
    IdentitySectionProps,
    | "isView"
    | "editingService"
    | "formData"
    | "onInputChange"
    | "descriptionError"
    | "markBlurred"
  >
>): React.ReactElement {
  if (isView) {
    return (
      <ReadOnlyField label="Service Description" fullWidth>
        {formData.serviceDescription || "—"}
      </ReadOnlyField>
    );
  }
  return (
    <FormControl isInvalid={!!descriptionError}>
      <FieldLabel hint={FIELD_HINTS.service.description.tip}>
        Service Description
      </FieldLabel>
      <Textarea
        value={formData.serviceDescription || ""}
        onChange={(e) => onInputChange("serviceDescription", e.target.value)}
        onBlur={() => markBlurred("serviceDescription")}
        placeholder={FIELD_HINTS.service.description.placeholder}
        bg="white"
        rows={3}
        maxLength={SERVICE_DESCRIPTION_MAX_LEN}
      />
      {descriptionError ? (
        <FormErrorMessage>{descriptionError}</FormErrorMessage>
      ) : (
        <FieldHint show={!editingService}>
          {FIELD_HINTS.service.description.helper(
            (formData.serviceDescription || "").trim().length,
            SERVICE_DESCRIPTION_MIN_LEN,
            SERVICE_DESCRIPTION_MAX_LEN,
          )}
        </FieldHint>
      )}
    </FormControl>
  );
}

function ServiceFormIdentitySection({
  isView,
  editingService,
  formData,
  onInputChange,
  isLlmTaskType,
  showServiceName,
  nameError,
  descriptionError,
  idError,
  markBlurred,
}: IdentitySectionProps): React.ReactElement {
  return (
    <VStack align="stretch" spacing={4}>
      {showServiceName ? (
        <ServiceNameField
          isView={isView}
          editingService={editingService}
          formData={formData}
          onInputChange={onInputChange}
          nameError={nameError}
          markBlurred={markBlurred}
        />
      ) : null}
      <ServiceIdField
        isView={isView}
        editingService={editingService}
        formData={formData}
        onInputChange={onInputChange}
        isLlmTaskType={isLlmTaskType}
        idError={idError}
        markBlurred={markBlurred}
      />
      <ServiceDescriptionField
        isView={isView}
        editingService={editingService}
        formData={formData}
        onInputChange={onInputChange}
        descriptionError={descriptionError}
        markBlurred={markBlurred}
      />
    </VStack>
  );
}

function AuthTokenField({
  isView,
  editingService,
  authToken,
  handleAuthTokenChange,
  hasAuthToken,
  isShowingSavedAuthMask,
  showAuthToken,
  onToggleShowAuthToken,
  authTokenFieldCopy,
}: Readonly<
  Pick<
    ConnectionSectionProps,
    | "isView"
    | "editingService"
    | "authToken"
    | "handleAuthTokenChange"
    | "hasAuthToken"
    | "isShowingSavedAuthMask"
    | "showAuthToken"
    | "onToggleShowAuthToken"
    | "authTokenFieldCopy"
  >
>): React.ReactElement | null {
  if (isView) {
    return (
      <ReadOnlyField label="Authentication Token">
        {hasAuthToken ? "Configured" : "Not configured"}
      </ReadOnlyField>
    );
  }
  const authCopy = authTokenFieldCopy({
    isEditing: Boolean(editingService),
    hasAuthToken,
  });
  return (
    <FormControl>
      <FieldLabel hint={authCopy.tip}>Authentication Token</FieldLabel>
      <InputGroup>
        <Input
          type={isShowingSavedAuthMask || showAuthToken ? "text" : "password"}
          value={authToken}
          onChange={(e) => handleAuthTokenChange(e.target.value)}
          placeholder={FIELD_HINTS.service.authToken.placeholder}
          bg="white"
          autoComplete="new-password"
          spellCheck={false}
          pr={isShowingSavedAuthMask ? undefined : "4.5rem"}
        />
        {!isShowingSavedAuthMask && (
          <InputRightElement width="4.5rem">
            <IconButton
              aria-label={
                showAuthToken
                  ? "Hide authentication token"
                  : "Show authentication token"
              }
              icon={showAuthToken ? <ViewIcon /> : <ViewOffIcon />}
              h="1.75rem"
              size="sm"
              type="button"
              onClick={onToggleShowAuthToken}
              variant="ghost"
            />
          </InputRightElement>
        )}
      </InputGroup>
      <FieldHint show={Boolean(authCopy.helper)}>{authCopy.helper}</FieldHint>
    </FormControl>
  );
}

function ServiceFormConnectionSection({
  isView,
  editingService,
  formData,
  onInputChange,
  isLlmTaskType,
  authToken,
  handleAuthTokenChange,
  hasAuthToken,
  isShowingSavedAuthMask,
  showAuthToken,
  onToggleShowAuthToken,
  infraError,
  markBlurred,
  authTokenFieldCopy,
}: ConnectionSectionProps): React.ReactElement {
  return (
    <VStack align="stretch" spacing={4}>
      {isView ? (
        <ReadOnlyField label="Endpoint" fullWidth>
          {formData.endpoint || "—"}
        </ReadOnlyField>
      ) : (
        <FormControl isRequired>
          <FieldLabel
            hint={
              isLlmTaskType
                ? FIELD_HINTS.service.endpoint.llmTip
                : FIELD_HINTS.service.endpoint.tip
            }
          >
            Endpoint
          </FieldLabel>
          <Input
            value={formData.endpoint || ""}
            onChange={(e) => onInputChange("endpoint", e.target.value)}
            placeholder={
              isLlmTaskType
                ? FIELD_HINTS.service.endpoint.llmPlaceholder
                : FIELD_HINTS.service.endpoint.placeholder
            }
            bg="white"
          />
          <FieldHint show={isLlmTaskType}>
            {FIELD_HINTS.service.endpoint.llmHelper}
          </FieldHint>
        </FormControl>
      )}

      {isLlmTaskType ? (
        <AuthTokenField
          isView={isView}
          editingService={editingService}
          authToken={authToken}
          handleAuthTokenChange={handleAuthTokenChange}
          hasAuthToken={hasAuthToken}
          isShowingSavedAuthMask={isShowingSavedAuthMask}
          showAuthToken={showAuthToken}
          onToggleShowAuthToken={onToggleShowAuthToken}
          authTokenFieldCopy={authTokenFieldCopy}
        />
      ) : null}

      {isView ? (
        <ReadOnlyField label="Hardware Description">
          {formData.hardwareDescription || "—"}
        </ReadOnlyField>
      ) : (
        <FormControl isInvalid={!!infraError}>
          <FieldLabel hint={FIELD_HINTS.service.hardware.tip}>
            Hardware Description
          </FieldLabel>
          <Input
            value={formData.hardwareDescription || ""}
            onChange={(e) =>
              onInputChange("hardwareDescription", e.target.value)
            }
            onBlur={() => markBlurred("hardwareDescription")}
            placeholder={FIELD_HINTS.service.hardware.placeholder}
            bg="white"
            maxLength={INFRA_DESCRIPTION_MAX_LEN}
          />
          {infraError ? (
            <FormErrorMessage>{infraError}</FormErrorMessage>
          ) : (
            <FieldHint>
              {FIELD_HINTS.service.hardware.helper(
                INFRA_DESCRIPTION_MIN_LEN,
                INFRA_DESCRIPTION_MAX_LEN,
              )}
            </FieldHint>
          )}
        </FormControl>
      )}
    </VStack>
  );
}

function TierPickerField({
  selectedTiers,
  selectedTierNames,
  onToggleTier,
  availableTiers,
  filteredTiers,
  unlistedSelectedTiers,
  tierSearch,
  onTierSearchChange,
}: Readonly<
  Pick<
    BillingSectionProps,
    | "selectedTiers"
    | "selectedTierNames"
    | "onToggleTier"
    | "availableTiers"
    | "filteredTiers"
    | "unlistedSelectedTiers"
    | "tierSearch"
    | "onTierSearchChange"
  >
>): React.ReactElement {
  const emptyMessage =
    availableTiers.length === 0
      ? "No tiers available"
      : "No tiers match your search";
  return (
    <FormControl isRequired>
      <FieldLabel hint={FIELD_HINTS.service.tier.tip}>Tier</FieldLabel>
      <Menu
        closeOnSelect={false}
        matchWidth
        onClose={() => onTierSearchChange("")}
      >
        <MenuButton
          as={Button}
          type="button"
          rightIcon={<ChevronDownIcon />}
          w="full"
          maxW="full"
          textAlign="left"
          fontWeight="normal"
          variant="outline"
          colorScheme="gray"
          color="ink.800"
          bg="white"
          borderColor="inherit"
          _hover={{ borderColor: "ink.300" }}
          fontSize="sm"
          justifyContent="space-between"
        >
          <Text as="span" isTruncated display="block" minW={0}>
            {selectedTierNames.length > 0
              ? selectedTierNames.join(", ")
              : FIELD_HINTS.service.tier.placeholder}
          </Text>
        </MenuButton>
        <Portal>
          <MenuList maxH="320px" overflow="hidden" p={0} zIndex={1500}>
            <Box px={3} py={2} borderBottomWidth="1px" borderColor="ink.100">
              <InputGroup size="sm">
                <InputLeftElement pointerEvents="none">
                  <SearchIcon color="ink.400" />
                </InputLeftElement>
                <Input
                  placeholder={FIELD_HINTS.service.tierSearch.placeholder}
                  value={tierSearch}
                  onChange={(e) => onTierSearchChange(e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                  onKeyDown={(e) => e.stopPropagation()}
                  bg="white"
                />
              </InputGroup>
            </Box>
            <Box maxH="240px" overflowY="auto" py={1}>
              {filteredTiers.length === 0 &&
              unlistedSelectedTiers.length === 0 ? (
                <Text px={3} py={2} fontSize="sm" color="ink.500">
                  {emptyMessage}
                </Text>
              ) : (
                <>
                  {filteredTiers.map((tier) => (
                    <MenuItem
                      key={tier.id}
                      onClick={() => onToggleTier(tier.id)}
                      closeOnSelect={false}
                    >
                      <Checkbox
                        isChecked={selectedTiers.includes(tier.id)}
                        onChange={() => onToggleTier(tier.id)}
                        onClick={(e) => e.stopPropagation()}
                        mr={2}
                      />
                      {tier.name}
                    </MenuItem>
                  ))}
                  {unlistedSelectedTiers.map((tier) => (
                    <MenuItem
                      key={tier.id}
                      onClick={() => onToggleTier(tier.id)}
                      closeOnSelect={false}
                    >
                      <Checkbox
                        isChecked
                        onChange={() => onToggleTier(tier.id)}
                        onClick={(e) => e.stopPropagation()}
                        mr={2}
                      />
                      <Text as="span" mr={2}>
                        {tier.name}
                      </Text>
                      <Badge colorScheme="orange" fontSize="xs">
                        Not listed
                      </Badge>
                    </MenuItem>
                  ))}
                </>
              )}
            </Box>
          </MenuList>
        </Portal>
      </Menu>
    </FormControl>
  );
}

function UnitTypeField({
  isView,
  formData,
  unitType,
}: Readonly<
  Pick<BillingSectionProps, "isView" | "formData" | "unitType">
>): React.ReactElement {
  if (isView) {
    return <ReadOnlyField label="Unit Type">{unitType || "—"}</ReadOnlyField>;
  }
  return (
    <FormControl>
      <FieldLabel hint={FIELD_HINTS.service.unitType.tip}>Unit Type</FieldLabel>
      <Input
        value={unitType}
        isReadOnly
        bg="ink.50"
        placeholder={
          formData.task_type ? "—" : FIELD_HINTS.service.unitType.needTaskType
        }
      />
    </FormControl>
  );
}

function UnitSizeField({
  isView,
  unitSize,
  onUnitSizeChange,
  unitSizeSelectOptions,
  isLlmTaskType,
}: Readonly<
  Pick<
    BillingSectionProps,
    | "isView"
    | "unitSize"
    | "onUnitSizeChange"
    | "unitSizeSelectOptions"
    | "isLlmTaskType"
  >
>): React.ReactElement {
  if (isView) {
    return (
      <ReadOnlyField label="Unit Size">
        {unitSize ? Number(unitSize).toLocaleString() : "N/A"}
      </ReadOnlyField>
    );
  }
  const unitSizeTip = isLlmTaskType
    ? FIELD_HINTS.service.unitSize.llmTip
    : FIELD_HINTS.service.unitSize.tip;
  return (
    <FormControl isRequired>
      <FieldLabel hint={unitSizeTip}>Unit Size</FieldLabel>
      <Select
        value={unitSize}
        onChange={(e) => onUnitSizeChange(e.target.value)}
        placeholder={FIELD_HINTS.service.unitSize.placeholder}
        bg="white"
      >
        {unitSizeSelectOptions.map((size) => (
          <option key={size} value={size}>
            {Number(size).toLocaleString()}
          </option>
        ))}
      </Select>
    </FormControl>
  );
}

function CurrencyField({
  isView,
  currency,
  onCurrencyChange,
}: Readonly<
  Pick<BillingSectionProps, "isView" | "currency" | "onCurrencyChange">
>): React.ReactElement {
  if (isView) {
    return <ReadOnlyField label="Currency">{currency || "INR"}</ReadOnlyField>;
  }
  return (
    <FormControl isRequired>
      <FieldLabel>Currency</FieldLabel>
      <Select
        value={currency}
        onChange={(e) => onCurrencyChange(e.target.value)}
        bg="white"
      >
        {CURRENCY_OPTIONS.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </Select>
    </FormControl>
  );
}

function BillingTierField({
  isView,
  selectedTiers,
  selectedTierNames,
  onToggleTier,
  availableTiers,
  filteredTiers,
  unlistedSelectedTiers,
  tierSearch,
  onTierSearchChange,
}: Readonly<
  Pick<
    BillingSectionProps,
    | "isView"
    | "selectedTiers"
    | "selectedTierNames"
    | "onToggleTier"
    | "availableTiers"
    | "filteredTiers"
    | "unlistedSelectedTiers"
    | "tierSearch"
    | "onTierSearchChange"
  >
>): React.ReactElement {
  if (isView) {
    if (selectedTierNames.length === 0) {
      return <ReadOnlyField label="Tier">N/A</ReadOnlyField>;
    }
    return (
      <ReadOnlyField label="Tier">
        <HStack spacing={1} flexWrap="wrap">
          {selectedTierNames.map((name) => (
            <Badge key={name} colorScheme="gray" fontSize="xs" px={2} py={0.5}>
              {name}
            </Badge>
          ))}
        </HStack>
      </ReadOnlyField>
    );
  }
  return (
    <TierPickerField
      selectedTiers={selectedTiers}
      selectedTierNames={selectedTierNames}
      onToggleTier={onToggleTier}
      availableTiers={availableTiers}
      filteredTiers={filteredTiers}
      unlistedSelectedTiers={unlistedSelectedTiers}
      tierSearch={tierSearch}
      onTierSearchChange={onTierSearchChange}
    />
  );
}

function ServiceFormBillingSection({
  isView,
  formData,
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
  unitSizeSelectOptions,
  currency,
  onCurrencyChange,
  selectedTiers,
  selectedTierNames,
  onToggleTier,
  availableTiers,
  filteredTiers,
  unlistedSelectedTiers,
  tierSearch,
  onTierSearchChange,
  isLlmTaskType,
  renderPriceField,
}: BillingSectionProps): React.ReactElement {
  const priceLabel = isLlmTaskType ? LLM_INPUT_PRICE_LABEL : PRICE_LABEL;
  const priceHelper = isLlmTaskType
    ? FIELD_HINTS.service.llmInputPrice.helper
    : FIELD_HINTS.service.price.helper;
  const priceTip = isLlmTaskType
    ? FIELD_HINTS.service.llmInputPrice.tip
    : FIELD_HINTS.service.price.tip;
  const pricePlaceholder = isLlmTaskType
    ? FIELD_HINTS.service.llmInputPrice.placeholder
    : FIELD_HINTS.service.price.placeholder;

  return (
    <VStack align="stretch" spacing={4}>
      <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
        <UnitTypeField isView={isView} formData={formData} unitType={unitType} />
        <UnitSizeField
          isView={isView}
          unitSize={unitSize}
          onUnitSizeChange={onUnitSizeChange}
          unitSizeSelectOptions={unitSizeSelectOptions}
          isLlmTaskType={isLlmTaskType}
        />
      </SimpleGrid>

      <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
        {renderPriceField(
          "pricePerUnit",
          priceLabel,
          pricePerUnit,
          pricePerUnitError,
          onPricePerUnitChange,
          priceHelper,
          pricePlaceholder,
          priceTip,
        )}
        <CurrencyField
          isView={isView}
          currency={currency}
          onCurrencyChange={onCurrencyChange}
        />
      </SimpleGrid>

      {isLlmTaskType ? (
        <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
          {renderPriceField(
            "cachedInputPricePerUnit",
            LLM_CACHED_INPUT_PRICE_LABEL,
            cachedInputPricePerUnit,
            cachedInputPricePerUnitError,
            onCachedInputPricePerUnitChange,
            FIELD_HINTS.service.llmCachedInputPrice.helper,
            FIELD_HINTS.service.llmCachedInputPrice.placeholder,
            FIELD_HINTS.service.llmCachedInputPrice.tip,
          )}
          {renderPriceField(
            "outputPricePerUnit",
            LLM_OUTPUT_PRICE_LABEL,
            outputPricePerUnit,
            outputPricePerUnitError,
            onOutputPricePerUnitChange,
            FIELD_HINTS.service.llmOutputPrice.helper,
            FIELD_HINTS.service.llmOutputPrice.placeholder,
            FIELD_HINTS.service.llmOutputPrice.tip,
          )}
        </SimpleGrid>
      ) : null}

      <BillingTierField
        isView={isView}
        selectedTiers={selectedTiers}
        selectedTierNames={selectedTierNames}
        onToggleTier={onToggleTier}
        availableTiers={availableTiers}
        filteredTiers={filteredTiers}
        unlistedSelectedTiers={unlistedSelectedTiers}
        tierSearch={tierSearch}
        onTierSearchChange={onTierSearchChange}
      />
    </VStack>
  );
}

export function ServiceFormFields(
  props: Readonly<ServiceFormFieldsProps>,
): React.ReactElement {
  return (
    <VStack spacing={8} align="stretch">
      <ServiceFormModelSection
        isView={props.isView}
        editingService={props.editingService}
        formData={props.formData}
        onTaskTypeChange={props.onTaskTypeChange}
        onModelNameChange={props.onModelNameChange}
        taskTypeNames={props.taskTypeNames}
        isLoadingModels={props.isLoadingModels}
        filteredModelsForDropdown={props.filteredModelsForDropdown}
        isCreateFormModelSelected={props.isCreateFormModelSelected}
        formatSubmissionDateDisplay={props.formatSubmissionDateDisplay}
        modelNamePlaceholder={props.modelNamePlaceholder}
      />
      <ServiceFormIdentitySection
        isView={props.isView}
        editingService={props.editingService}
        formData={props.formData}
        onInputChange={props.onInputChange}
        isLlmTaskType={props.isLlmTaskType}
        showServiceName={props.showServiceName}
        nameError={props.nameError}
        descriptionError={props.descriptionError}
        idError={props.idError}
        markBlurred={props.markBlurred}
      />
      <ServiceFormConnectionSection
        isView={props.isView}
        editingService={props.editingService}
        formData={props.formData}
        onInputChange={props.onInputChange}
        isLlmTaskType={props.isLlmTaskType}
        authToken={props.authToken}
        handleAuthTokenChange={props.handleAuthTokenChange}
        hasAuthToken={props.hasAuthToken}
        isShowingSavedAuthMask={props.isShowingSavedAuthMask}
        showAuthToken={props.showAuthToken}
        onToggleShowAuthToken={props.onToggleShowAuthToken}
        infraError={props.infraError}
        markBlurred={props.markBlurred}
        authTokenFieldCopy={props.authTokenFieldCopy}
      />
      <ServiceFormBillingSection
        isView={props.isView}
        formData={props.formData}
        unitType={props.unitType}
        pricePerUnit={props.pricePerUnit}
        pricePerUnitError={props.pricePerUnitError}
        onPricePerUnitChange={props.onPricePerUnitChange}
        cachedInputPricePerUnit={props.cachedInputPricePerUnit}
        cachedInputPricePerUnitError={props.cachedInputPricePerUnitError}
        onCachedInputPricePerUnitChange={props.onCachedInputPricePerUnitChange}
        outputPricePerUnit={props.outputPricePerUnit}
        outputPricePerUnitError={props.outputPricePerUnitError}
        onOutputPricePerUnitChange={props.onOutputPricePerUnitChange}
        unitSize={props.unitSize}
        onUnitSizeChange={props.onUnitSizeChange}
        unitSizeSelectOptions={props.unitSizeSelectOptions}
        currency={props.currency}
        onCurrencyChange={props.onCurrencyChange}
        selectedTiers={props.selectedTiers}
        selectedTierNames={props.selectedTierNames}
        onToggleTier={props.onToggleTier}
        availableTiers={props.availableTiers}
        filteredTiers={props.filteredTiers}
        unlistedSelectedTiers={props.unlistedSelectedTiers}
        tierSearch={props.tierSearch}
        onTierSearchChange={props.onTierSearchChange}
        isLlmTaskType={props.isLlmTaskType}
        renderPriceField={props.renderPriceField}
      />
    </VStack>
  );
}
