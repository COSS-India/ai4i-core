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
import React from "react";
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
  authTokenFieldHint: (options: {
    isEditing: boolean;
    hasAuthToken: boolean;
  }) => string;
  renderPriceField: (
    field: string,
    label: string,
    value: string,
    error: string | null | undefined,
    onChange: (value: string) => void,
    helper: string,
    placeholder?: string,
  ) => React.ReactNode;
};

function useFields(props: ServiceFormFieldsProps): ServiceFormFieldsProps {
  return props;
}

function ServiceFormModelSection(props: ServiceFormFieldsProps): React.ReactElement {
  const {
    isView, editingService, formData, onInputChange, onTaskTypeChange, onModelNameChange,
    taskTypeNames, isLoadingModels, filteredModelsForDropdown, unitType,
    pricePerUnit, pricePerUnitError, onPricePerUnitChange,
    cachedInputPricePerUnit, cachedInputPricePerUnitError, onCachedInputPricePerUnitChange,
    outputPricePerUnit, outputPricePerUnitError, onOutputPricePerUnitChange,
    unitSize, onUnitSizeChange, unitSizeSelectOptions, currency, onCurrencyChange,
    selectedTiers, selectedTierNames, onToggleTier, availableTiers, filteredTiers,
    unlistedSelectedTiers, tierSearch, onTierSearchChange, isCreateFormModelSelected,
    isLlmTaskType, showServiceName, authToken, handleAuthTokenChange, hasAuthToken,
    isShowingSavedAuthMask, showAuthToken, onToggleShowAuthToken,
    nameError, descriptionError, infraError, idError, markBlurred,
    formatSubmissionDateDisplay, modelNamePlaceholder, authTokenFieldHint, renderPriceField,
  } = props;
  return (
              <VStack align="stretch" spacing={4}>
              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                {isView ? (
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
                ) : (
                <FormControl isRequired>
                  <FieldLabel>Task Type</FieldLabel>
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
                )}

                {isView ? (
                  <ReadOnlyField label="Model Name">
                    {formData.modelName || formData.modelId || "—"}
                  </ReadOnlyField>
                ) : (
                <FormControl isRequired>
                  <FieldLabel>Model Name</FieldLabel>
                  {editingService ? (
                    <Input
                      value={formData.modelName || formData.modelId || ""}
                      isReadOnly
                      bg="ink.50"
                    />
                  ) : (
                    <Select
                      value={formData.modelId || ""}
                      onChange={(e) => onModelNameChange(e.target.value)}
                      placeholder={
                        isLoadingModels
                          ? FIELD_HINTS.service.modelName.loading
                          : !formData.task_type
                            ? FIELD_HINTS.service.modelName.needTaskType
                            : FIELD_HINTS.service.modelName.placeholder
                      }
                      bg="white"
                      isDisabled={isLoadingModels || !formData.task_type}
                    >
                      {filteredModelsForDropdown.map((model) => (
                        <option
                          key={model.modelId || model.model_id}
                          value={model.modelId || model.model_id}
                        >
                          {model.name || model.modelId || model.model_id}
                        </option>
                      ))}
                    </Select>
                  )}
                </FormControl>
                )}
              </SimpleGrid>

              {/* 3. Model ID + Model Submission Date — FYI plain text (not disabled inputs) */}
              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                {isView ? (
                  <ReadOnlyField label="Model ID">
                    {formData.modelId || "—"}
                  </ReadOnlyField>
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
                    {formatSubmissionDateDisplay(
                      formData.modelSubmissionDate as string | undefined,
                    )}
                  </ReadOnlyField>
                ) : (
                <FormControl>
                  <FieldLabel>Model Submission Date</FieldLabel>
                  <Text
                    fontSize="sm"
                    color={
                      formData.modelSubmissionDate ? "ink.800" : "ink.500"
                    }
                  >
                    {isCreateFormModelSelected
                      ? formatSubmissionDateDisplay(
                          formData.modelSubmissionDate as string | undefined,
                        )
                      : FIELD_HINTS.service.modelId.empty}
                  </Text>
                </FormControl>
                )}
              </SimpleGrid>
              </VStack>
  );
}

function ServiceFormIdentitySection(props: ServiceFormFieldsProps): React.ReactElement {
  const {
    isView, editingService, formData, onInputChange, onTaskTypeChange, onModelNameChange,
    taskTypeNames, isLoadingModels, filteredModelsForDropdown, unitType,
    pricePerUnit, pricePerUnitError, onPricePerUnitChange,
    cachedInputPricePerUnit, cachedInputPricePerUnitError, onCachedInputPricePerUnitChange,
    outputPricePerUnit, outputPricePerUnitError, onOutputPricePerUnitChange,
    unitSize, onUnitSizeChange, unitSizeSelectOptions, currency, onCurrencyChange,
    selectedTiers, selectedTierNames, onToggleTier, availableTiers, filteredTiers,
    unlistedSelectedTiers, tierSearch, onTierSearchChange, isCreateFormModelSelected,
    isLlmTaskType, showServiceName, authToken, handleAuthTokenChange, hasAuthToken,
    isShowingSavedAuthMask, showAuthToken, onToggleShowAuthToken,
    nameError, descriptionError, infraError, idError, markBlurred,
    formatSubmissionDateDisplay, modelNamePlaceholder, authTokenFieldHint, renderPriceField,
  } = props;
  return (
              <VStack align="stretch" spacing={4}>
              {showServiceName && isView ? (
                <ReadOnlyField label="Service Name">{formData.name || "—"}</ReadOnlyField>
              ) : null}
              {showServiceName && !isView && (
                <FormControl isRequired isInvalid={!!nameError}>
                  <FieldLabel>Service Name</FieldLabel>
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
              )}

              {isView ? (
                <ReadOnlyField label="Service ID">{formData.serviceId || "—"}</ReadOnlyField>
              ) : (
              <FormControl isRequired isInvalid={!!idError}>
                <FieldLabel>Service ID</FieldLabel>
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
                {idError ? (
                  <FormErrorMessage>{idError}</FormErrorMessage>
                ) : (
                  <FieldHint show={!editingService}>
                    {isLlmTaskType
                      ? FIELD_HINTS.service.serviceId.llmHelper
                      : FIELD_HINTS.service.serviceId.helper}
                  </FieldHint>
                )}
              </FormControl>
              )}

              {isView ? (
                <ReadOnlyField label="Service Description" fullWidth>
                  {formData.serviceDescription || "—"}
                </ReadOnlyField>
              ) : (
              <FormControl isInvalid={!!descriptionError}>
                <FieldLabel>Service Description</FieldLabel>
                <Textarea
                  value={formData.serviceDescription || ""}
                  onChange={(e) =>
                    onInputChange("serviceDescription", e.target.value)
                  }
                  onBlur={() => markBlurred("serviceDescription")}
                  placeholder={FIELD_HINTS.service.description.placeholder}
                  bg="white"
                  rows={4}
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
              )}

              </VStack>
  );
}

function ServiceFormConnectionSection(props: ServiceFormFieldsProps): React.ReactElement {
  const {
    isView, editingService, formData, onInputChange, onTaskTypeChange, onModelNameChange,
    taskTypeNames, isLoadingModels, filteredModelsForDropdown, unitType,
    pricePerUnit, pricePerUnitError, onPricePerUnitChange,
    cachedInputPricePerUnit, cachedInputPricePerUnitError, onCachedInputPricePerUnitChange,
    outputPricePerUnit, outputPricePerUnitError, onOutputPricePerUnitChange,
    unitSize, onUnitSizeChange, unitSizeSelectOptions, currency, onCurrencyChange,
    selectedTiers, selectedTierNames, onToggleTier, availableTiers, filteredTiers,
    unlistedSelectedTiers, tierSearch, onTierSearchChange, isCreateFormModelSelected,
    isLlmTaskType, showServiceName, authToken, handleAuthTokenChange, hasAuthToken,
    isShowingSavedAuthMask, showAuthToken, onToggleShowAuthToken,
    nameError, descriptionError, infraError, idError, markBlurred,
    formatSubmissionDateDisplay, modelNamePlaceholder, authTokenFieldHint, renderPriceField,
  } = props;
  return (
              <VStack align="stretch" spacing={4}>
              {isView ? (
                <ReadOnlyField label="Endpoint" fullWidth>
                  {formData.endpoint || "—"}
                </ReadOnlyField>
              ) : (
              <FormControl isRequired>
                <FieldLabel>Endpoint</FieldLabel>
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
                <FieldHint>
                  {isLlmTaskType
                    ? FIELD_HINTS.service.endpoint.llmHelper
                    : FIELD_HINTS.service.endpoint.helper}
                </FieldHint>
              </FormControl>
              )}

              {isLlmTaskType && isView ? (
                <ReadOnlyField label="Authentication Token">
                  {hasAuthToken ? "Configured" : "Not configured"}
                </ReadOnlyField>
              ) : null}
              {isLlmTaskType && !isView && (
                <FormControl>
                  <FieldLabel>Authentication Token</FieldLabel>
                  <InputGroup>
                    <Input
                      type={
                        isShowingSavedAuthMask || showAuthToken
                          ? "text"
                          : "password"
                      }
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
                  <FieldHint>
                    {editingService
                      ? hasAuthToken
                        ? FIELD_HINTS.service.authToken.editHelper
                        : FIELD_HINTS.service.authToken.editEmptyHelper
                      : FIELD_HINTS.service.authToken.helper}
                  </FieldHint>
                </FormControl>
              )}

              {isView ? (
                <ReadOnlyField label="Hardware Description">
                  {formData.hardwareDescription || "—"}
                </ReadOnlyField>
              ) : (
              <FormControl isInvalid={!!infraError}>
                <FieldLabel>Hardware Description</FieldLabel>
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

function ServiceFormBillingSection(props: ServiceFormFieldsProps): React.ReactElement {
  const {
    isView, editingService, formData, onInputChange, onTaskTypeChange, onModelNameChange,
    taskTypeNames, isLoadingModels, filteredModelsForDropdown, unitType,
    pricePerUnit, pricePerUnitError, onPricePerUnitChange,
    cachedInputPricePerUnit, cachedInputPricePerUnitError, onCachedInputPricePerUnitChange,
    outputPricePerUnit, outputPricePerUnitError, onOutputPricePerUnitChange,
    unitSize, onUnitSizeChange, unitSizeSelectOptions, currency, onCurrencyChange,
    selectedTiers, selectedTierNames, onToggleTier, availableTiers, filteredTiers,
    unlistedSelectedTiers, tierSearch, onTierSearchChange, isCreateFormModelSelected,
    isLlmTaskType, showServiceName, authToken, handleAuthTokenChange, hasAuthToken,
    isShowingSavedAuthMask, showAuthToken, onToggleShowAuthToken,
    nameError, descriptionError, infraError, idError, markBlurred,
    formatSubmissionDateDisplay, modelNamePlaceholder, authTokenFieldHint, renderPriceField,
  } = props;
  return (
              <VStack align="stretch" spacing={4}>
              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                  {isView ? (
                    <ReadOnlyField label="Unit Type">{unitType || "—"}</ReadOnlyField>
                  ) : (
                  <FormControl>
                    <FieldLabel>Unit Type</FieldLabel>
                    <Input
                      value={unitType}
                      isReadOnly
                      bg="ink.50"
                      placeholder={
                        formData.task_type
                          ? "—"
                          : FIELD_HINTS.service.unitType.needTaskType
                      }
                    />
                    <FieldHint>{FIELD_HINTS.service.unitType.helper}</FieldHint>
                  </FormControl>
                  )}

                  {isView ? (
                    <ReadOnlyField label="Unit Size">
                      {unitSize ? Number(unitSize).toLocaleString() : "N/A"}
                    </ReadOnlyField>
                  ) : (
                  <FormControl isRequired>
                    <FieldLabel>Unit Size</FieldLabel>
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
                    <FieldHint>
                      {isLlmTaskType
                        ? FIELD_HINTS.service.unitSize.llmHelper
                        : FIELD_HINTS.service.unitSize.helper}
                    </FieldHint>
                  </FormControl>
                  )}
                </SimpleGrid>

              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                  {renderPriceField(
                    "pricePerUnit",
                    isLlmTaskType ? LLM_INPUT_PRICE_LABEL : PRICE_LABEL,
                    pricePerUnit,
                    pricePerUnitError,
                    onPricePerUnitChange,
                    isLlmTaskType
                      ? FIELD_HINTS.service.llmInputPrice.helper
                      : FIELD_HINTS.service.price.helper,
                    isLlmTaskType
                      ? FIELD_HINTS.service.llmInputPrice.placeholder
                      : FIELD_HINTS.service.price.placeholder,
                  )}

                  {isView ? (
                    <ReadOnlyField label="Currency">{currency || "INR"}</ReadOnlyField>
                  ) : (
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
                  )}
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
                  )}
                  {renderPriceField(
                    "outputPricePerUnit",
                    LLM_OUTPUT_PRICE_LABEL,
                    outputPricePerUnit,
                    outputPricePerUnitError,
                    onOutputPricePerUnitChange,
                    FIELD_HINTS.service.llmOutputPrice.helper,
                    FIELD_HINTS.service.llmOutputPrice.placeholder,
                  )}
                </SimpleGrid>
              ) : null}
              {isView ? (
                <ReadOnlyField label="Tier">
                  {selectedTierNames.length > 0 ? (
                    <HStack spacing={1} flexWrap="wrap">
                      {selectedTierNames.map((name) => (
                        <Badge key={name} colorScheme="gray" fontSize="xs" px={2} py={0.5}>
                          {name}
                        </Badge>
                      ))}
                    </HStack>
                  ) : (
                    "N/A"
                  )}
                </ReadOnlyField>
              ) : (
              <FormControl isRequired>
                <FieldLabel>Tier</FieldLabel>
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
                      <Box
                        px={3}
                        py={2}
                        borderBottomWidth="1px"
                        borderColor="ink.100"
                      >
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
                          <Text
                            px={3}
                            py={2}
                            fontSize="sm"
                            color="ink.500"
                          >
                            {availableTiers.length === 0
                              ? "No tiers available"
                              : "No tiers match your search"}
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
                <FieldHint>{FIELD_HINTS.service.tier.helper}</FieldHint>
              </FormControl>
              )}
              </VStack>
  );
}

export function ServiceFormFields(props: ServiceFormFieldsProps): React.ReactElement {
  return (
    <VStack spacing={8} align="stretch">
      <ServiceFormModelSection {...props} />
      <ServiceFormIdentitySection {...props} />
      <ServiceFormConnectionSection {...props} />
      <ServiceFormBillingSection {...props} />
    </VStack>
  );
}
