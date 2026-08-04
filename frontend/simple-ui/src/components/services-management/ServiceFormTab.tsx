// Create/Edit Service tab: single form shared between create and edit modes
// Field order & LLM vs non-LLM Service ID behavior: AI4IDS-2692
import {
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Checkbox,
  FormControl,
  FormErrorMessage,
  FormLabel,
  Heading,
  HStack,
  Input,
  InputGroup,
  InputLeftElement,
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
import { ChevronDownIcon, SearchIcon } from "@chakra-ui/icons";
import React, { useMemo, useState } from "react";
import { formatModelTaskTypeLabel } from "../../config/constants";
import type { Service } from "../../services/servicesManagementService";
import type { ModelDetails } from "../../types/platform";
import type { Tier } from "../../types/tierManagement";

/** Billing unit-size presets shown as a dropdown (AI4IDS-2692). */
export const UNIT_SIZE_OPTIONS = ["1", "100", "1000", "1000000"] as const;

/** Currency reference list for the create form. */
export const CURRENCY_OPTIONS = ["INR"] as const;

interface ServiceFormTabProps {
  cardBg: string;
  cardBorder: string;
  editingService: Service | null;
  formData: Partial<Service>;
  onInputChange: (field: keyof Service, value: string) => void;
  onTaskTypeChange: (taskType: string) => void;
  onModelNameChange: (modelId: string) => void;
  taskTypeNames: string[];
  isLoadingModels: boolean;
  filteredModelsForDropdown: ModelDetails[];
  unitType: string;
  unitTypeOptions: string[];
  onUnitTypeChange: (value: string) => void;
  pricePerUnit: string;
  onPricePerUnitChange: (value: string) => void;
  unitSize: string;
  onUnitSizeChange: (value: string) => void;
  currency: string;
  onCurrencyChange: (value: string) => void;
  selectedTiers: string[];
  onToggleTier: (tierId: string) => void;
  availableTiers: Tier[];
  isCreateFormModelSelected: boolean;
  canCreateService: boolean;
  isLlmTaskType: boolean;
  serviceIdError?: string | null;
  isSubmitting: boolean;
  onSubmit: (e: React.FormEvent) => void;
  onCancel: () => void;
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

const ServiceFormTab: React.FC<ServiceFormTabProps> = ({
  cardBg,
  cardBorder,
  editingService,
  formData,
  onInputChange,
  onTaskTypeChange,
  onModelNameChange,
  taskTypeNames,
  isLoadingModels,
  filteredModelsForDropdown,
  unitType,
  unitTypeOptions,
  onUnitTypeChange,
  pricePerUnit,
  onPricePerUnitChange,
  unitSize,
  onUnitSizeChange,
  currency,
  onCurrencyChange,
  selectedTiers,
  onToggleTier,
  availableTiers,
  isCreateFormModelSelected,
  canCreateService,
  isLlmTaskType,
  serviceIdError,
  isSubmitting,
  onSubmit,
  onCancel,
}) => {
  const unitSizeSelectOptions = useMemo(() => {
    const opts: string[] = [...UNIT_SIZE_OPTIONS];
    if (unitSize && !opts.includes(unitSize)) {
      opts.push(unitSize);
    }
    return opts;
  }, [unitSize]);

  const [tierSearch, setTierSearch] = useState("");
  const filteredTiers = useMemo(() => {
    const q = tierSearch.trim().toLowerCase();
    if (!q) return availableTiers;
    return availableTiers.filter((tier) =>
      (tier.name || "").toLowerCase().includes(q),
    );
  }, [availableTiers, tierSearch]);

  const showServiceName = !isLlmTaskType;

  return (
    <Card
      bg={cardBg}
      borderColor={cardBorder}
      borderWidth="1px"
      boxShadow="none"
    >
      <CardHeader>
        <Heading size="md" color="gray.700" userSelect="none" cursor="default">
          {editingService
            ? `Edit Service — ${editingService.name || editingService.serviceId || editingService.service_id}`
            : "Create New Service"}
        </Heading>
        {editingService && (
          <Text fontSize="sm" color="gray.500" mt={1}>
            Update pricing and tier mapping. Service metadata is read-only.
          </Text>
        )}
      </CardHeader>
      <CardBody>
        <form onSubmit={onSubmit}>
          <VStack spacing={6} align="stretch">
            {/* 1. Model Task Type | 2. Model Name */}
            <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
              <FormControl isRequired>
                <FormLabel fontWeight="semibold">Model Task Type</FormLabel>
                {editingService ? (
                  <Input
                    value={formatModelTaskTypeLabel(formData.task_type || "")}
                    isReadOnly
                    bg="gray.50"
                  />
                ) : (
                  <Select
                    value={formData.task_type || ""}
                    onChange={(e) => onTaskTypeChange(e.target.value)}
                    placeholder="Select a task type"
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

              <FormControl isRequired>
                <FormLabel fontWeight="semibold">Model Name</FormLabel>
                {editingService ? (
                  <Input
                    value={formData.modelName || formData.modelId || ""}
                    isReadOnly
                    bg="gray.50"
                  />
                ) : (
                  <Select
                    value={formData.modelId || ""}
                    onChange={(e) => onModelNameChange(e.target.value)}
                    placeholder={
                      isLoadingModels
                        ? "Loading models..."
                        : !formData.task_type
                          ? "Select a task type first"
                          : "Select a model"
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
            </SimpleGrid>

            {/* 3. Model ID + Model Submission Date — FYI plain text (not disabled inputs) */}
            <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
              <Box>
                <Text fontSize="sm" fontWeight="semibold" color="gray.700" mb={1}>
                  Model ID
                </Text>
                <Text
                  fontSize="sm"
                  color={isCreateFormModelSelected ? "gray.800" : "gray.500"}
                >
                  {formData.modelId || "Select a model above"}
                </Text>
              </Box>
              <Box>
                <Text fontSize="sm" fontWeight="semibold" color="gray.700" mb={1}>
                  Model Submission Date
                </Text>
                <Text
                  fontSize="sm"
                  color={
                    formData.modelSubmissionDate ? "gray.800" : "gray.500"
                  }
                >
                  {isCreateFormModelSelected
                    ? formatSubmissionDateDisplay(
                        formData.modelSubmissionDate as string | undefined,
                      )
                    : "Select a model above"}
                </Text>
              </Box>
            </SimpleGrid>

            {/* Service Name (non-LLM) + Service ID */}
            {showServiceName && (
              <FormControl isRequired>
                <FormLabel fontWeight="semibold">Service Name</FormLabel>
                <Input
                  value={formData.name || ""}
                  onChange={(e) => onInputChange("name", e.target.value)}
                  placeholder="Enter service name e.g. asr-conformer-gpu"
                  bg={editingService ? "gray.50" : "white"}
                  isReadOnly={!!editingService}
                />
                {!editingService && (
                  <Text fontSize="xs" color="gray.500" mt={1}>
                    Enter service name e.g. asr-conformer-gpu.
                  </Text>
                )}
              </FormControl>
            )}

            <FormControl isRequired isInvalid={!!serviceIdError}>
              <FormLabel fontWeight="semibold">Service ID</FormLabel>
              <Input
                value={formData.serviceId || ""}
                onChange={(e) => {
                  // LLM Service ID is also sent as Service Name; BE name rules
                  // allow only alphanumeric, /, and - (no underscore).
                  const allowed = isLlmTaskType
                    ? /[^a-zA-Z0-9/-]/g
                    : /[^a-zA-Z0-9/_-]/g;
                  onInputChange("serviceId", e.target.value.replaceAll(allowed, ""));
                }}
                placeholder={
                  isLlmTaskType && formData.modelName
                    ? `${formData.modelName}/…`
                    : "Enter service id"
                }
                bg={editingService ? "gray.50" : "white"}
                isReadOnly={!!editingService}
              />
              {isLlmTaskType && !editingService && (
                <Text fontSize="xs" color="gray.500" mt={1}>
                  Pre-filled with the selected model name as a prefix. Complete
                  the Service ID; it is also used as the Service Name.
                </Text>
              )}
              {serviceIdError && (
                <FormErrorMessage>{serviceIdError}</FormErrorMessage>
              )}
            </FormControl>

            {/* Service Description */}
            <FormControl isRequired>
              <FormLabel fontWeight="semibold">Service Description</FormLabel>
              <Textarea
                value={formData.serviceDescription || ""}
                onChange={(e) =>
                  onInputChange("serviceDescription", e.target.value)
                }
                placeholder="Provide a brief description of what this service does"
                bg="white"
                rows={4}
              />
            </FormControl>

            {/* Endpoint */}
            <FormControl isRequired>
              <FormLabel fontWeight="semibold">Endpoint</FormLabel>
              <Input
                value={formData.endpoint || ""}
                onChange={(e) => onInputChange("endpoint", e.target.value)}
                placeholder="Enter endpoint URL, e.g. http://localhost:8088"
                bg="white"
              />
              <Text fontSize="xs" color="gray.500" mt={1}>
                Enter the full HTTP endpoint where this service is hosted.
              </Text>
            </FormControl>

            {/* 4. Unit Type + Unit Size (grouped dropdowns) */}
            <Box>
              <Text fontSize="sm" fontWeight="semibold" color="gray.700" mb={3}>
                Unit Type &amp; Unit Size
              </Text>
              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                <FormControl isRequired>
                  <FormLabel fontWeight="semibold">Unit Type</FormLabel>
                  <Select
                    value={unitType}
                    onChange={(e) => onUnitTypeChange(e.target.value)}
                    placeholder={
                      formData.task_type
                        ? "Select unit type"
                        : "Select a task type first"
                    }
                    bg="white"
                    isDisabled={!formData.task_type || unitTypeOptions.length === 0}
                  >
                    {unitTypeOptions.map((u) => (
                      <option key={u} value={u}>
                        {u}
                      </option>
                    ))}
                  </Select>
                </FormControl>

                <FormControl isRequired>
                  <FormLabel fontWeight="semibold">Unit Size</FormLabel>
                  <Select
                    value={unitSize}
                    onChange={(e) => onUnitSizeChange(e.target.value)}
                    placeholder="Select unit size"
                    bg="white"
                  >
                    {unitSizeSelectOptions.map((size) => (
                      <option key={size} value={size}>
                        {Number(size).toLocaleString()}
                      </option>
                    ))}
                  </Select>
                </FormControl>
              </SimpleGrid>
            </Box>

            {/* 5. Price per Unit + Currency (grouped) */}
            <Box>
              <Text fontSize="sm" fontWeight="semibold" color="gray.700" mb={3}>
                Price per Unit &amp; Currency
              </Text>
              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                <FormControl isRequired>
                  <FormLabel fontWeight="semibold">Price per Unit</FormLabel>
                  <Input
                    value={pricePerUnit}
                    onChange={(e) => onPricePerUnitChange(e.target.value)}
                    placeholder="e.g. 600"
                    type="number"
                    min={0}
                    bg="white"
                  />
                </FormControl>

                <FormControl isRequired>
                  <FormLabel fontWeight="semibold">Currency</FormLabel>
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
              </SimpleGrid>
            </Box>

            {/* Tier */}
            <FormControl>
              <FormLabel fontWeight="semibold">
                Tier{" "}
                <Box as="span" color="red.500">
                  *
                </Box>
              </FormLabel>
              <Menu
                closeOnSelect={false}
                matchWidth
                onClose={() => setTierSearch("")}
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
                  bg="white"
                  borderColor="inherit"
                  _hover={{ borderColor: "gray.300" }}
                  fontSize="sm"
                  justifyContent="space-between"
                >
                  <Text as="span" isTruncated display="block" minW={0}>
                    {selectedTiers.length > 0
                      ? selectedTiers
                          .map(
                            (id) =>
                              availableTiers.find((t) => t.id === id)?.name ??
                              id,
                          )
                          .join(", ")
                      : "Select Tiers"}
                  </Text>
                </MenuButton>
                <Portal>
                  <MenuList maxH="320px" overflow="hidden" p={0}>
                    <Box
                      px={3}
                      py={2}
                      borderBottomWidth="1px"
                      borderColor="gray.100"
                    >
                      <InputGroup size="sm">
                        <InputLeftElement pointerEvents="none">
                          <SearchIcon color="gray.400" />
                        </InputLeftElement>
                        <Input
                          placeholder="Search tiers..."
                          value={tierSearch}
                          onChange={(e) => setTierSearch(e.target.value)}
                          onClick={(e) => e.stopPropagation()}
                          onKeyDown={(e) => e.stopPropagation()}
                          bg="white"
                        />
                      </InputGroup>
                    </Box>
                    <Box maxH="240px" overflowY="auto" py={1}>
                      {filteredTiers.length === 0 ? (
                        <Text
                          px={3}
                          py={2}
                          fontSize="sm"
                          color="gray.500"
                        >
                          {availableTiers.length === 0
                            ? "No tiers available"
                            : "No tiers match your search"}
                        </Text>
                      ) : (
                        filteredTiers.map((tier) => (
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
                        ))
                      )}
                    </Box>
                  </MenuList>
                </Portal>
              </Menu>
            </FormControl>

            <HStack justify="flex-end" spacing={4} pt={4}>
              <Button type="button" variant="outline" onClick={onCancel}>
                {editingService ? "Cancel" : "Reset"}
              </Button>
              <Button
                type="submit"
                colorScheme="blue"
                isLoading={isSubmitting}
                loadingText={editingService ? "Saving..." : "Creating..."}
                isDisabled={!canCreateService || isSubmitting}
              >
                {editingService ? "Save Changes" : "Create Service"}
              </Button>
            </HStack>
          </VStack>
        </form>
      </CardBody>
    </Card>
  );
};

export default ServiceFormTab;
