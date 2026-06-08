import {
  Badge,
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Heading,
  HStack,
  SimpleGrid,
  Switch,
  Text,
  Tooltip,
  VStack,
} from "@chakra-ui/react";
import React from "react";
import {
  formatModelVersionStatusLabel,
  isModelVersionStatusActive,
} from "../../config/constants";
import type { UseModelManagementReturn } from "../../hooks/useModelManagement";
import { getTaskColor } from "./utils";

export function ModelViewDrawer(props: UseModelManagementReturn) {
  const {
    cardBg,
    cardBorder,
    selectedModel,
    isRegistryReadOnly,
    router,
    modelIdsWithPublishedService,
    updatingModelId,
    openConfirmDialog,
    isEditingModel,
  } = props;

  if (!selectedModel) return null;

  return (
    <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
      <CardHeader>
        <HStack justify="space-between" align="center">
          <Heading size="md" color="gray.700" userSelect="none" cursor="default">
            {selectedModel.name}
          </Heading>
          <HStack spacing={2}>
            {!isRegistryReadOnly &&
              (selectedModel.versionStatus?.toLowerCase() === "active" || !selectedModel.versionStatus) && (
                <Button
                  size="sm"
                  colorScheme="blue"
                  onClick={() => {
                    router.push(`/services-management?modelId=${selectedModel.modelId}&tab=create`);
                  }}
                >
                  Create Service
                </Button>
              )}
            {!isRegistryReadOnly &&
            (selectedModel.versionStatus?.toLowerCase() === "active" || !selectedModel.versionStatus) &&
            !modelIdsWithPublishedService.has(selectedModel.modelId) ? (
              <Tooltip label="Deprecate model" placement="top" hasArrow>
                <Box as="span" display="inline-flex" alignItems="center">
                  <Switch
                    size="md"
                    colorScheme="green"
                    isChecked={true}
                    onChange={() => openConfirmDialog("deprecate", selectedModel)}
                    isDisabled={updatingModelId !== null}
                  />
                </Box>
              </Tooltip>
            ) : selectedModel.versionStatus?.toLowerCase() !== "active" && selectedModel.versionStatus ? (
              <Tooltip label="Activate model" placement="top" hasArrow>
                <Box as="span" display="inline-flex" alignItems="center">
                  <Switch
                    size="md"
                    colorScheme="green"
                    isChecked={false}
                    onChange={() => openConfirmDialog("activate", selectedModel)}
                    isDisabled={updatingModelId !== null}
                  />
                </Box>
              </Tooltip>
            ) : null}
          </HStack>
        </HStack>
      </CardHeader>
      <CardBody>
        {!isEditingModel && (
          <VStack spacing={6} align="stretch">
            {isRegistryReadOnly && (
              <Badge colorScheme="gray" alignSelf="flex-start" fontSize="sm" px={2} py={1}>
                Read-only
              </Badge>
            )}
            <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
              <Box>
                <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                  Model ID
                </Text>
                <Text fontSize="md" wordBreak="break-all">
                  {selectedModel.modelId}
                </Text>
              </Box>
              <Box>
                <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                  Model name
                </Text>
                <Text fontSize="md">{selectedModel.name}</Text>
              </Box>
              <Box>
                <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                  Version
                </Text>
                <Text fontSize="md">{selectedModel.version || "1.0"}</Text>
              </Box>
              <Box>
                <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                  Status
                </Text>
                <Badge
                  colorScheme={isModelVersionStatusActive(selectedModel.versionStatus) ? "green" : "gray"}
                  fontSize="sm"
                  p={2}
                >
                  {formatModelVersionStatusLabel(selectedModel.versionStatus)}
                </Badge>
              </Box>
              <Box>
                <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                  Task type
                </Text>
                <Badge colorScheme={getTaskColor(selectedModel.task.type)} fontSize="sm" p={2}>
                  {selectedModel.task.type.toUpperCase()}
                </Badge>
              </Box>
            </SimpleGrid>

            <Box>
              <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                Description
              </Text>
              <Text fontSize="md">{selectedModel.description || "—"}</Text>
            </Box>

            <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
              <Box>
                <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                  License
                </Text>
                <Text fontSize="md">{selectedModel.license || "—"}</Text>
              </Box>
              <Box>
                <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                  Source
                </Text>
                <Text fontSize="md">{selectedModel.source || "—"}</Text>
              </Box>
            </SimpleGrid>

            <Box>
              <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={2}>
                Domain
              </Text>
              <HStack spacing={2} flexWrap="wrap">
                {selectedModel.domain && selectedModel.domain.length > 0 ? (
                  selectedModel.domain.map((domain, idx) => (
                    <Badge key={idx} fontSize="sm" colorScheme="gray" p={2}>
                      {domain}
                    </Badge>
                  ))
                ) : (
                  <Text color="gray.500" fontSize="sm">
                    No domains specified
                  </Text>
                )}
              </HStack>
            </Box>
          </VStack>
        )}
        {/* Editing disabled for models after creation - edit form removed */}
      </CardBody>
    </Card>
  );
}
