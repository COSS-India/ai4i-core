// Create/Edit Service tab: single form shared between create and edit modes
import {
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Checkbox,
  FormControl,
  FormLabel,
  Grid,
  Heading,
  HStack,
  Input,
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
import { ChevronDownIcon } from "@chakra-ui/icons";
import React from "react";
import { formatModelTaskTypeLabel } from "../../config/constants";
import type { Service } from "../../services/servicesManagementService";
import type { ModelDetails } from "../../types/platform";
import type { Tier } from "../../types/tierManagement";

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
  pricePerUnit: string;
  onPricePerUnitChange: (value: string) => void;
  unitSize: string;
  onUnitSizeChange: (value: string) => void;
  selectedTiers: string[];
  onToggleTier: (tierId: string) => void;
  availableTiers: Tier[];
  isCreateFormModelSelected: boolean;
  canCreateService: boolean;
  isSubmitting: boolean;
  onSubmit: (e: React.FormEvent) => void;
  onCancel: () => void;
}

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
  pricePerUnit,
  onPricePerUnitChange,
  unitSize,
  onUnitSizeChange,
  selectedTiers,
  onToggleTier,
  availableTiers,
  isCreateFormModelSelected,
  canCreateService,
  isSubmitting,
  onSubmit,
  onCancel,
}) => {
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
            {/* Service Name */}
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

            {/* Service Id */}
            <FormControl isRequired>
              <FormLabel fontWeight="semibold">Service Id</FormLabel>
              <Input
                value={formData.serviceId || ""}
                onChange={(e) =>
                  onInputChange(
                    "serviceId",
                    e.target.value.replace(/[^a-zA-Z0-9/_-]/g, ""),
                  )
                }
                placeholder="Enter service id"
                bg={editingService ? "gray.50" : "white"}
                isReadOnly={!!editingService}
              />
              {!editingService && (
                <Text fontSize="xs" color="gray.500" mt={1}>
                  Letters, numbers, and / _ - only.
                </Text>
              )}
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

            {/* Model Task Type | Model Name */}
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

            {/* Unit type | Price per Unit | Currency | Tier */}
            <SimpleGrid columns={{ base: 2, md: 4 }} spacing={4}>
              <FormControl>
                <FormLabel fontWeight="semibold">Unit type</FormLabel>
                <Input
                  value={unitType}
                  isReadOnly
                  bg="gray.50"
                  placeholder="—"
                />
              </FormControl>

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

              <FormControl>
                <FormLabel fontWeight="semibold">Currency</FormLabel>
                <Input value="INR" isReadOnly bg="gray.50" />
              </FormControl>

              <FormControl>
                <FormLabel fontWeight="semibold">
                  Tier{" "}
                  <Box as="span" color="red.500">
                    *
                  </Box>
                </FormLabel>
                <Menu closeOnSelect={false} matchWidth>
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
                    <MenuList maxH="280px" overflowY="auto">
                      {availableTiers.map((tier) => (
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
                    </MenuList>
                  </Portal>
                </Menu>
              </FormControl>
            </SimpleGrid>

            {/* Unit Size | Model ID | Model Submission Date */}
            <Grid
              templateColumns={{ base: "1fr", md: "1fr 1.5fr 1.5fr" }}
              gap={4}
            >
              <FormControl isRequired>
                <FormLabel fontWeight="semibold">Unit Size</FormLabel>
                <Input
                  value={unitSize}
                  onChange={(e) => onUnitSizeChange(e.target.value)}
                  placeholder="e.g. 100"
                  type="number"
                  min={1}
                  step={1}
                  bg="white"
                />
              </FormControl>

              <FormControl isRequired>
                <FormLabel fontWeight="semibold">Model ID</FormLabel>
                <Input
                  value={formData.modelId || ""}
                  bg={isCreateFormModelSelected ? "gray.50" : "white"}
                  isReadOnly
                  placeholder="Select a model above"
                />
              </FormControl>

              <FormControl>
                <FormLabel fontWeight="semibold">
                  Model Submission Date
                </FormLabel>
                <Input
                  type="date"
                  value={(formData.modelSubmissionDate as string) || ""}
                  bg={isCreateFormModelSelected ? "gray.50" : "white"}
                  isReadOnly
                />
              </FormControl>
            </Grid>

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
