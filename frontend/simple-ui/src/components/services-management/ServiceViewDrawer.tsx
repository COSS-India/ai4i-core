import React from "react";
import {
  Badge,
  Box,
  Card,
  CardBody,
  CardHeader,
  Heading,
  HStack,
  IconButton,
  SimpleGrid,
  Text,
  Tooltip,
  VStack,
} from "@chakra-ui/react";
import { FaUpload, FaDownload } from "react-icons/fa";
import { getTaskColor, isServiceModelDeprecated } from "./utils";
import type { UseServicesManagementReturn } from "../../hooks/useServicesManagement";

export type ServiceViewDrawerProps = UseServicesManagementReturn;

export default function ServiceViewDrawer(sm: ServiceViewDrawerProps) {
  if (!sm.isViewingService || !sm.selectedService) {
    return null;
  }

  const selectedService = sm.selectedService;

  return (
    <Card bg={sm.cardBg} borderColor={sm.cardBorder} borderWidth="1px" boxShadow="none">
      <CardHeader>
        <Heading size="md" color="gray.700" userSelect="none" cursor="default">
          {selectedService.name || selectedService.serviceId || selectedService.service_id}
        </Heading>
      </CardHeader>
      <CardBody>
        {!sm.isEditingService && (
          <VStack spacing={6} align="stretch">
            {sm.isRegistryReadOnly && (
              <Badge colorScheme="gray" alignSelf="flex-start" fontSize="sm" px={2} py={1}>
                Read-only
              </Badge>
            )}
            <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
              <Box>
                <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                  Service ID
                </Text>
                <Text fontSize="md">{selectedService.serviceId || selectedService.service_id || "N/A"}</Text>
              </Box>
              <Box>
                <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                  Name
                </Text>
                <Text fontSize="md">{selectedService.name || "N/A"}</Text>
              </Box>
            </SimpleGrid>

            <Box>
              <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                Description
              </Text>
              <Text fontSize="md">{selectedService.serviceDescription || selectedService.description || "N/A"}</Text>
            </Box>

            <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
              <Box>
                <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                  Model Task Type
                </Text>
                <Badge
                  colorScheme={getTaskColor(selectedService?.model?.task?.type || selectedService?.task?.type || selectedService.task_type)}
                  fontSize="sm"
                  p={2}
                >
                  {(selectedService?.model?.task?.type || selectedService?.task?.type || selectedService.task_type)?.toUpperCase() || "N/A"}
                </Badge>
              </Box>
              <Box>
                <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                  Status (Publish/Unpublish)
                </Text>
                <HStack spacing={2} align="center" flexWrap="wrap">
                  <Badge
                    colorScheme={selectedService.isPublished === true ? "green" : "gray"}
                    fontSize="sm"
                    p={2}
                  >
                    {selectedService.isPublished === true ? "Published" : "Unpublished"}
                  </Badge>
                  {!sm.isRegistryReadOnly &&
                    (selectedService.isPublished === true ? (
                      <Tooltip label="Unpublish" placement="top" hasArrow>
                        <IconButton
                          aria-label="Unpublish"
                          icon={<FaDownload />}
                          size="sm"
                          colorScheme="red"
                          variant="outline"
                          onClick={() => { sm.setConfirmUnpublishService(selectedService); sm.onUnpublishConfirmOpen(); }}
                          isLoading={sm.unpublishingServiceUuid === selectedService.serviceId}
                          isDisabled={sm.unpublishingServiceUuid !== null || sm.publishingServiceUuid !== null}
                        />
                      </Tooltip>
                    ) : (
                      <Tooltip
                        label={isServiceModelDeprecated(selectedService) || sm.selectedServiceModelDeprecated === true ? "This service cannot be published because its associated model is deprecated. Restore the model to ACTIVE before publishing." : "Publish"}
                        hasArrow
                        placement="top"
                      >
                        <Box as="span" display="inline-block">
                          <IconButton
                            aria-label="Publish"
                            icon={<FaUpload />}
                            size="sm"
                            colorScheme="green"
                            variant="outline"
                            onClick={() => { sm.setConfirmPublishService(selectedService); sm.onPublishConfirmOpen(); }}
                            isLoading={sm.publishingServiceUuid === selectedService.serviceId}
                            isDisabled={
                              sm.unpublishingServiceUuid !== null ||
                              sm.publishingServiceUuid !== null ||
                              isServiceModelDeprecated(selectedService) ||
                              sm.selectedServiceModelDeprecated === true
                            }
                          />
                        </Box>
                      </Tooltip>
                    ))}
                </HStack>
              </Box>
            </SimpleGrid>

            <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
              <Box>
                <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                  Model ID
                </Text>
                <Text fontSize="md">{selectedService.modelId || selectedService.model_id || "N/A"}</Text>
              </Box>
              <Box>
                <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                  Endpoint
                </Text>
                <Text fontSize="md" wordBreak="break-all">
                  {selectedService.endpoint || selectedService.endpoint_url || "N/A"}
                </Text>
              </Box>
            </SimpleGrid>

            <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
              <Box>
                <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                  Hardware Description
                </Text>
                <Text fontSize="md">{selectedService.hardwareDescription || "N/A"}</Text>
              </Box>
              <Box>
                <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                  Published On
                </Text>
                <Text fontSize="md">
                  {selectedService.publishedOn
                    ? new Date(selectedService.publishedOn * 1000).toLocaleString()
                    : "N/A"}
                </Text>
              </Box>
            </SimpleGrid>

            {selectedService.created_at && (
              <Box>
                <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                  Created At
                </Text>
                <Text fontSize="md">
                  {new Date(selectedService.created_at).toLocaleString()}
                </Text>
              </Box>
            )}

            {selectedService.updated_at && (
              <Box>
                <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                  Updated At
                </Text>
                <Text fontSize="md">
                  {new Date(selectedService.updated_at).toLocaleString()}
                </Text>
              </Box>
            )}
          </VStack>
        )}
      </CardBody>
    </Card>
  );
}
