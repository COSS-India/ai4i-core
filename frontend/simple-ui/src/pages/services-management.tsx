// Services Management page with list, create, view, update, and delete functionality

import {
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  FormControl,
  FormLabel,
  Heading,
  Input,
  Select,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Badge,
  Text,
  VStack,
  HStack,
  useColorModeValue,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
  useToast,
  Textarea,
  SimpleGrid,
  Grid,
  AlertDialog,
  AlertDialogBody,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogContent,
  AlertDialogOverlay,
  useDisclosure,
} from "@chakra-ui/react";
import Head from "next/head";
import { useRouter } from "next/router";
import { useQueryClient } from "@tanstack/react-query";
import React, { useState, useEffect, useRef } from "react";
import ContentLayout from "../components/common/ContentLayout";
import {
  listServices,
  createService,
  getServiceById,
  updateService,
  deleteService,
  Service,
} from "../services/servicesManagementService";
import { getAllModels, getModelById } from "../services/modelManagementService";
import { useAuth } from "../hooks/useAuth";
import { useSessionExpiry } from "../hooks/useSessionExpiry";
import { extractErrorInfo } from "../utils/errorHandler";

const ServicesManagementPage: React.FC = () => {
  const [services, setServices] = useState<Service[]>([]);
  const [models, setModels] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingModels, setIsLoadingModels] = useState(false);
  const [selectedService, setSelectedService] = useState<Service | null>(null);
  const [isViewingService, setIsViewingService] = useState(false);
  const [isEditingService, setIsEditingService] = useState(false);
  const [formData, setFormData] = useState<Partial<Service>>({
    name: "",
    serviceDescription: "",
    publishedOn: Math.floor(Date.now() / 1000),
    modelId: "",
    modelName: "", // Store selected model name for display
    endpoint: "",
    task_type: "",
    modelVersion: "1.0",
  });
  const [updateFormData, setUpdateFormData] = useState<Partial<Service>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [deletingServiceUuid, setDeletingServiceUuid] = useState<string | null>(null);
  const [publishingServiceUuid, setPublishingServiceUuid] = useState<string | null>(null);
  const [unpublishingServiceUuid, setUnpublishingServiceUuid] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState(0);
  const toast = useToast();
  const queryClient = useQueryClient();
  const {  user } = useAuth();
  const { checkSessionExpiry } = useSessionExpiry();
  const router = useRouter();
  
  // Check if user is GUEST and redirect if so
  useEffect(() => {
    if (user?.roles?.includes('GUEST')) {
      toast({
        title: "Access Denied",
        description: "Guest users do not have access to Services Management.",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      router.push('/');
    }
  }, [user, router, toast]);
  const { isOpen, onOpen, onClose } = useDisclosure();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const [serviceToDelete, setServiceToDelete] = useState<Service | null>(null);
  // Model fetched by ID when navigating from a deprecated model's "Create Service" (not in active list)
  const [preselectedModelFromQuery, setPreselectedModelFromQuery] = useState<any | null>(null);

  // Fetch services on component mount
  useEffect(() => {
    const fetchServices = async () => {
      setIsLoading(true);
      try {
        const fetchedServices = await listServices();
        setServices(fetchedServices);
      } catch (error: any) {
        console.error("Failed to fetch services:", error);
        
        // Use centralized error handler
        const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(error);
        
        toast({
          title: showOnlyMessage ? undefined : errorTitle,
          description: errorMessage,
          status: "error",
          duration: 5000,
          isClosable: true,
        });
        setServices([]);
      } finally {
        setIsLoading(false);
      }
    };

    fetchServices();
  }, [toast]);

  // Fetch models on component mount (for dropdown)
  useEffect(() => {
    const fetchModels = async () => {
      setIsLoadingModels(true);
      try {
        const fetchedModels = await getAllModels();
        // Filter to only show ACTIVE models
        const activeModels = fetchedModels.filter(
          (model) => model.versionStatus?.toLowerCase() === "active" || !model.versionStatus
        );
        setModels(activeModels);
      } catch (error: any) {
        console.error("Failed to fetch models:", error);
        // Don't show toast for models - it's not critical for the page to work
        setModels([]);
      } finally {
        setIsLoadingModels(false);
      }
    };

    fetchModels();
  }, []);

  // Handle query parameters for pre-selecting model from model-management page
  useEffect(() => {
    const { modelId, tab } = router.query;
    if (!modelId || typeof modelId !== "string") return;

    const runPreselect = async () => {
      // Switch to Create Service tab if specified
      if (tab === "create") {
        setActiveTab(1);
      }

      const inActiveList = models.some(
        (m) => (m.modelId || m.model_id) === modelId
      );
      if (inActiveList && formData.modelId !== modelId) {
        handleModelNameChange(modelId);
        router.replace("/services-management", undefined, { shallow: true });
        return;
      }

      // Model not in active list (e.g. DEPRECATED) - fetch by ID and add to dropdown
      if (!inActiveList) {
        try {
          const modelDetails = await getModelById(modelId);
          if (modelDetails) {
            setPreselectedModelFromQuery(modelDetails);
            if (formData.modelId !== modelId) {
              handleModelNameChange(modelId);
            }
          }
        } catch (e) {
          console.error("Failed to load preselected model:", e);
        }
        router.replace("/services-management", undefined, { shallow: true });
      }
    };

    if (models.length > 0) {
      runPreselect();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router.query, models]);

  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");
  const tableBg = useColorModeValue("white", "gray.800");
  const tableHeaderBg = useColorModeValue("gray.50", "gray.700");
  const tableRowHoverBg = useColorModeValue("gray.50", "gray.700");

  // Dropdown options: active models + preselected model from query (e.g. deprecated) if not already in list
  const modelsForDropdown =
    preselectedModelFromQuery &&
    !models.some(
      (m) =>
        (m.modelId || m.model_id) ===
        (preselectedModelFromQuery.modelId || preselectedModelFromQuery.model_id)
    )
      ? [preselectedModelFromQuery, ...models]
      : models;

  const getTaskColor = (taskType?: string) => {
    if (!taskType) return "gray";
    switch (taskType.toLowerCase()) {
      case "asr":
        return "orange";
      case "nmt":
        return "green";
      case "tts":
        return "blue";
      case "llm":
        return "purple";
      default:
        return "gray";
    }
  };

  const getStatusColor = (status?: string) => {
    if (!status) return "gray";
    switch (status.toLowerCase()) {
      case "active":
        return "green";
      case "inactive":
        return "red";
      case "pending":
        return "yellow";
      default:
        return "gray";
    }
  };

  const handleInputChange = (
    field: keyof Service,
    value: string
  ) => {
    setFormData((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  // Handle model name selection and derive modelId, task_type, and modelVersion
  const handleModelNameChange = async (modelId: string) => {
    // Check session expiry before fetching model details
    if (!checkSessionExpiry()) return;
    if (modelId) {
      try {
        setIsLoadingModels(true);
        const modelDetails = await getModelById(modelId);
        
        // Extract task_type from model
        const taskType = modelDetails?.task?.type || modelDetails?.task_type || modelDetails?.taskType || "";
        
        // Extract model version (required field after migration)
        const modelVersion = modelDetails?.version || modelDetails?.modelVersion || "1.0";
        
        // Get model name for display
        const modelName = modelDetails?.name || modelDetails?.modelId || modelDetails?.model_id || "";
        
        setFormData((prev) => ({
          ...prev,
          modelId: modelId,
          modelName: modelName,
          task_type: taskType,
          modelVersion: modelVersion,
        }));
      } catch (error: any) {
        console.error("Failed to fetch model details:", error);
        toast({
          title: "Failed to Load Model",
          description: error instanceof Error ? error.message : "Failed to fetch model details",
          status: "warning",
          duration: 3000,
          isClosable: true,
        });
      } finally {
        setIsLoadingModels(false);
      }
    } else {
      // Clear fields if no model selected
      setFormData((prev) => ({
        ...prev,
        modelId: "",
        modelName: "",
        task_type: "",
        modelVersion: "",
      }));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Check session expiry before submitting
    if (!checkSessionExpiry()) return;
    
    setIsSubmitting(true);

    try {
      // Auto-generate serviceId from name and timestamp
      const timestamp = Date.now();
      const serviceId = `${formData.name?.toLowerCase().replace(/\s+/g, '-') || 'service'}-${timestamp}`;
      
      // Prepare service data with auto-generated serviceId
      const serviceData: Partial<Service> = {
        ...formData,
        serviceId: serviceId,
        publishedOn: Math.floor(Date.now() / 1000),
        hardwareDescription: 'Default hardware', // Default value since field is removed
        api_key: '', // Default empty since field is removed
        status: 'active', // Default status
      };

      const createdService = await createService(serviceData);

      // Invalidate all service-related queries to refresh service lists across all pages
      queryClient.invalidateQueries({ queryKey: ["asr-services"] });
      queryClient.invalidateQueries({ queryKey: ["tts-services"] });
      queryClient.invalidateQueries({ queryKey: ["ocr-services"] });
      queryClient.invalidateQueries({ queryKey: ["nmt-services"] });
      queryClient.invalidateQueries({ queryKey: ["nerServices"] });
      queryClient.invalidateQueries({ queryKey: ["llm-services"] });
      queryClient.invalidateQueries({ queryKey: ["transliteration-services"] });
      queryClient.invalidateQueries({ queryKey: ["speaker-diarization-services"] });
      queryClient.invalidateQueries({ queryKey: ["language-detection-services"] });
      queryClient.invalidateQueries({ queryKey: ["language-diarization-services"] });
      queryClient.invalidateQueries({ queryKey: ["audioLanguageDetectionServices"] });

      toast({
        title: "Service Created",
        description: "Service has been created successfully",
        status: "success",
        duration: 3000,
        isClosable: true,
      });

      // Reset form
      setFormData({
        name: "",
        serviceDescription: "",
        publishedOn: Math.floor(Date.now() / 1000),
        modelId: "",
        modelName: "",
        endpoint: "",
        task_type: "",
        modelVersion: "1.0",
      });
      setPreselectedModelFromQuery(null);

      // Refresh services list
      const fetchedServices = await listServices();
      setServices(fetchedServices);

      // Switch to list tab
      setActiveTab(0);
    } catch (error: any) {
      const { title: errorTitle, message: errorMsg, showOnlyMessage } = extractErrorInfo(error);
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMsg,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleViewService = async (serviceId: string) => {
    // Check session expiry before viewing service
    if (!checkSessionExpiry()) return;
    
    try {
      const service = await getServiceById(serviceId);
      setSelectedService(service);
      setUpdateFormData(service);
      setIsViewingService(true);
      setActiveTab(2);
    } catch (error: any) {
      const errorMessage = error instanceof Error ? error.message : "Failed to fetch service details";
      const { title: errorTitle, message: errorMsg, showOnlyMessage } = extractErrorInfo(error);
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMsg,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    }
  };

  const handleUpdateService = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Check session expiry before updating
    if (!checkSessionExpiry()) return;
    
    if (!selectedService?.uuid) {
      toast({
        title: "Update Failed",
        description: "Service UUID is required for update",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      return;
    }

    setIsUpdating(true);

    try {
      const updatedService = await updateService({
        ...updateFormData,
        uuid: selectedService.uuid,
      });

      // Invalidate all service-related queries to refresh service lists across all pages
      queryClient.invalidateQueries({ queryKey: ["asr-services"] });
      queryClient.invalidateQueries({ queryKey: ["tts-services"] });
      queryClient.invalidateQueries({ queryKey: ["ocr-services"] });
      queryClient.invalidateQueries({ queryKey: ["nmt-services"] });
      queryClient.invalidateQueries({ queryKey: ["nerServices"] });
      queryClient.invalidateQueries({ queryKey: ["llm-services"] });
      queryClient.invalidateQueries({ queryKey: ["transliteration-services"] });
      queryClient.invalidateQueries({ queryKey: ["speaker-diarization-services"] });
      queryClient.invalidateQueries({ queryKey: ["language-detection-services"] });
      queryClient.invalidateQueries({ queryKey: ["language-diarization-services"] });
      queryClient.invalidateQueries({ queryKey: ["audioLanguageDetectionServices"] });

      toast({
        title: "Service Updated",
        description: "Service has been updated successfully",
        status: "success",
        duration: 3000,
        isClosable: true,
      });

      setSelectedService(updatedService);
      setIsEditingService(false);

      // Refresh services list
      const fetchedServices = await listServices();
      setServices(fetchedServices);
    } catch (error: any) {
      const errorMessage = error instanceof Error ? error.message : "Failed to update service";
      const { title: errorTitle, message: errorMsg, showOnlyMessage } = extractErrorInfo(error);
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMsg,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsUpdating(false);
    }
  };

  const handlePublishService = async (service: Service) => {
    if (!service.serviceId) {
      toast({
        title: "Publish Failed",
        description: "Service ID is required",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      return;
    }

    setPublishingServiceUuid(service.uuid || service.serviceId);

    try {
      // Update service to set isPublished = true using PATCH with only serviceId and isPublished
      const updatedService = await updateService({
        serviceId: service.serviceId,
        isPublished: true,
      });

      toast({
        title: "Service Published",
        description: `Service ${service.name || service.serviceId} has been published successfully`,
        status: "success",
        duration: 3000,
        isClosable: true,
      });

      // Invalidate all service-related queries to refresh service lists across all pages
      queryClient.invalidateQueries({ queryKey: ["asr-services"] });
      queryClient.invalidateQueries({ queryKey: ["tts-services"] });
      queryClient.invalidateQueries({ queryKey: ["ocr-services"] });
      queryClient.invalidateQueries({ queryKey: ["nmt-services"] });
      queryClient.invalidateQueries({ queryKey: ["nerServices"] });
      queryClient.invalidateQueries({ queryKey: ["llm-services"] });
      queryClient.invalidateQueries({ queryKey: ["transliteration-services"] });
      queryClient.invalidateQueries({ queryKey: ["speaker-diarization-services"] });
      queryClient.invalidateQueries({ queryKey: ["language-detection-services"] });
      queryClient.invalidateQueries({ queryKey: ["language-diarization-services"] });
      queryClient.invalidateQueries({ queryKey: ["audioLanguageDetectionServices"] });

      // Refresh services list
      const fetchedServices = await listServices();
      setServices(fetchedServices);

      // Update selected service if it's the one being published
      if (selectedService?.uuid === service.uuid) {
        setSelectedService(updatedService);
      }
    } catch (error: any) {
      const errorMessage = error instanceof Error ? error.message : "Failed to publish service";
      const { title: errorTitle, message: errorMsg, showOnlyMessage } = extractErrorInfo(error);
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMsg,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setPublishingServiceUuid(null);
    }
  };

  const handleUnpublishService = async (service: Service) => {
    if (!service.serviceId) {
      toast({
        title: "Unpublish Failed",
        description: "Service ID is required",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      return;
    }

    setUnpublishingServiceUuid(service.uuid || service.serviceId);

    try {
      // Update service to set isPublished = false using PATCH with only serviceId and isPublished
      const updatedService = await updateService({
        serviceId: service.serviceId,
        isPublished: false,
      });

      toast({
        title: "Service Unpublished",
        description: `Service ${service.name || service.serviceId} has been unpublished successfully`,
        status: "success",
        duration: 3000,
        isClosable: true,
      });

      // Invalidate all service-related queries to refresh service lists across all pages
      queryClient.invalidateQueries({ queryKey: ["asr-services"] });
      queryClient.invalidateQueries({ queryKey: ["tts-services"] });
      queryClient.invalidateQueries({ queryKey: ["ocr-services"] });
      queryClient.invalidateQueries({ queryKey: ["nmt-services"] });
      queryClient.invalidateQueries({ queryKey: ["nerServices"] });
      queryClient.invalidateQueries({ queryKey: ["llm-services"] });
      queryClient.invalidateQueries({ queryKey: ["transliteration-services"] });
      queryClient.invalidateQueries({ queryKey: ["speaker-diarization-services"] });
      queryClient.invalidateQueries({ queryKey: ["language-detection-services"] });
      queryClient.invalidateQueries({ queryKey: ["language-diarization-services"] });
      queryClient.invalidateQueries({ queryKey: ["audioLanguageDetectionServices"] });

      // Refresh services list
      const fetchedServices = await listServices();
      setServices(fetchedServices);

      // Update selected service if it's the one being unpublished
      if (selectedService?.uuid === service.uuid) {
        setSelectedService(updatedService);
      }
    } catch (error: any) {
      const errorMessage = error instanceof Error ? error.message : "Failed to unpublish service";
      const { title: errorTitle, message: errorMsg, showOnlyMessage } = extractErrorInfo(error);
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMsg,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setUnpublishingServiceUuid(null);
    }
  };

  const handleDeleteClick = (service: Service) => {
    setServiceToDelete(service);
    onOpen();
  };

  const handleDeleteConfirm = async () => {
    // Check session expiry before deleting
    if (!checkSessionExpiry()) return;
    
    if (!serviceToDelete?.uuid) {
      toast({
        title: "Delete Failed",
        description: "Service UUID is required for deletion",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      onClose();
      return;
    }

    setDeletingServiceUuid(serviceToDelete.uuid);

    try {
      await deleteService(serviceToDelete.uuid);

      toast({
        title: "Service Deleted",
        description: `Service ${serviceToDelete.name || serviceToDelete.service_id} has been deleted successfully`,
        status: "success",
        duration: 3000,
        isClosable: true,
      });

      // Invalidate all service-related queries to refresh service lists across all pages
      queryClient.invalidateQueries({ queryKey: ["asr-services"] });
      queryClient.invalidateQueries({ queryKey: ["tts-services"] });
      queryClient.invalidateQueries({ queryKey: ["ocr-services"] });
      queryClient.invalidateQueries({ queryKey: ["nmt-services"] });
      queryClient.invalidateQueries({ queryKey: ["nerServices"] });
      queryClient.invalidateQueries({ queryKey: ["llm-services"] });
      queryClient.invalidateQueries({ queryKey: ["transliteration-services"] });
      queryClient.invalidateQueries({ queryKey: ["speaker-diarization-services"] });
      queryClient.invalidateQueries({ queryKey: ["language-detection-services"] });
      queryClient.invalidateQueries({ queryKey: ["language-diarization-services"] });
      queryClient.invalidateQueries({ queryKey: ["audioLanguageDetectionServices"] });

      // Refresh services list
      const fetchedServices = await listServices();
      setServices(fetchedServices);

      // If viewing the deleted service, close the view
      if (selectedService?.uuid === serviceToDelete.uuid) {
        setIsViewingService(false);
        setSelectedService(null);
        setActiveTab(0);
      }
    } catch (error: any) {
      const errorMessage = error instanceof Error ? error.message : "Failed to delete service";
      const { title: errorTitle, message: errorMsg, showOnlyMessage } = extractErrorInfo(error);
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMsg,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setDeletingServiceUuid(null);
      setServiceToDelete(null);
      onClose();
    }
  };

  return (
    <>
      <Head>
        <title>Services Management - AI4I Platform</title>
        <meta name="description" content="Manage and configure services" />
      </Head>

      <ContentLayout>
        <VStack spacing={6} w="full">
          {/* Page Header */}
          <Box textAlign="center" mb={2}>
            <Heading size="lg" color="gray.800" mb={1}>
              Services Management
            </Heading>
            <Text color="gray.600" fontSize="sm">
              Manage and configure services
            </Text>
          </Box>

          <Grid gap={8} w="full" mx="auto">
            <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px">
              <Tabs
                colorScheme="blue"
                variant="enclosed"
                index={activeTab}
                onChange={(index) => {
                  setActiveTab(index);
                  if (index !== 2) {
                    setIsViewingService(false);
                    setSelectedService(null);
                  }
                }}
              >
                <TabList>
                  <Tab fontWeight="semibold">List Services</Tab>
                  <Tab fontWeight="semibold">Create Service</Tab>
                  {isViewingService && (
                    <Tab fontWeight="semibold">View Service</Tab>
                  )}
                </TabList>

                <TabPanels>
                  {/* List Services Tab */}
                  <TabPanel px={0} pt={6}>
                    <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
                      <CardHeader>
                        <Heading size="md" color="gray.700">
                          All Services
                        </Heading>
                      </CardHeader>
                      <CardBody>
                        {isLoading ? (
                          <Box textAlign="center" py={8}>
                            <Text color="gray.500">Loading services...</Text>
                          </Box>
                        ) : (
                          <Box overflowX="auto">
                            <Table variant="simple" bg={tableBg}>
                              <Thead bg={tableHeaderBg}>
                                <Tr>
                                  <Th>Service ID</Th>
                                  <Th>Name</Th>
                                  <Th>Description</Th>
                                  <Th>Task Type</Th>
                                  <Th>Model ID</Th>
                                  <Th>Published Status</Th>
                                  <Th>Status</Th>
                                  <Th>Actions</Th>
                                </Tr>
                              </Thead>
                              <Tbody>
                                {services.map((service) => (
                                  <Tr
                                    key={service.uuid || service.service_id}
                                    _hover={{ bg: tableRowHoverBg, cursor: "pointer" }}
                                  >
                                    <Td>{service.serviceId || service.service_id || "N/A"}</Td>
                                    <Td>{service.name || "N/A"}</Td>
                                    <Td>
                                      <Text noOfLines={2} maxW="300px">
                                        {service.serviceDescription || service.description || "N/A"}
                                      </Text>
                                    </Td>
                                    <Td>
                                      <Badge
                                        colorScheme={getTaskColor(service.model?.task?.type || service.task?.type || service.task_type)}
                                        fontSize="sm"
                                        p={1}
                                      >
                                        {(service.model?.task?.type || service.task?.type || service.task_type)?.toUpperCase() || "N/A"}
                                      </Badge>
                                    </Td>
                                    <Td>{service.modelId || service.model_id || "N/A"}</Td>
                                    <Td>
                                      <Badge
                                        colorScheme={service.isPublished === true ? "green" : "gray"}
                                        fontSize="sm"
                                        p={1}
                                      >
                                        {service.isPublished === true ? "PUBLISHED" : "UNPUBLISHED"}
                                      </Badge>
                                    </Td>
                                    <Td>
                                      <Badge
                                        colorScheme={getStatusColor(service.healthStatus?.status || service.status)}
                                        fontSize="sm"
                                        p={1}
                                      >
                                        {(service.healthStatus?.status || service.status)?.toUpperCase() || "N/A"}
                                      </Badge>
                                    </Td>
                                    <Td onClick={(e) => e.stopPropagation()}>
                                      <HStack spacing={2}>
                                        <Button
                                          size="sm"
                                          colorScheme="blue"
                                          variant="outline"
                                          onClick={() => handleViewService(service.serviceId || service.service_id || "")}
                                        >
                                          View
                                        </Button>
                                        {service.isPublished === true ? (
                                          <Button
                                            size="sm"
                                            colorScheme="red"
                                            variant="outline"
                                            onClick={() => handleUnpublishService(service)}
                                            isLoading={unpublishingServiceUuid === service.uuid}
                                            loadingText="Unpublishing..."
                                            isDisabled={unpublishingServiceUuid !== null || publishingServiceUuid !== null}
                                          >
                                            Unpublish
                                          </Button>
                                        ) : (
                                          <Button
                                            size="sm"
                                            colorScheme="green"
                                            variant="outline"
                                            onClick={() => handlePublishService(service)}
                                            isLoading={publishingServiceUuid === service.uuid}
                                            loadingText="Publishing..."
                                            isDisabled={unpublishingServiceUuid !== null || publishingServiceUuid !== null}
                                          >
                                            Publish
                                          </Button>
                                        )}
                                        <Button
                                          size="sm"
                                          colorScheme="red"
                                          variant="outline"
                                          onClick={() => handleDeleteClick(service)}
                                          isLoading={deletingServiceUuid === service.uuid}
                                          loadingText="Deleting..."
                                          isDisabled={deletingServiceUuid !== null}
                                        >
                                          Delete
                                        </Button>
                                      </HStack>
                                    </Td>
                                  </Tr>
                                ))}
                              </Tbody>
                            </Table>
                          </Box>
                        )}
                        {!isLoading && services.length === 0 && (
                          <Box textAlign="center" py={8}>
                            <Text color="gray.500">No services found</Text>
                          </Box>
                        )}
                      </CardBody>
                    </Card>
                  </TabPanel>

                  {/* Create Service Tab */}
                  <TabPanel px={0} pt={6}>
                    <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
                      <CardHeader>
                        <Heading size="md" color="gray.700">
                          Create New Service
                        </Heading>
                      </CardHeader>
                      <CardBody>
                        <form onSubmit={handleSubmit}>
                          <VStack spacing={6} align="stretch">
                            <FormControl isRequired>
                              <FormLabel fontWeight="semibold">Name</FormLabel>
                              <Input
                                value={formData.name || ""}
                                onChange={(e) => handleInputChange("name", e.target.value)}
                                placeholder="Enter service name"
                                bg="white"
                              />
                              <Text fontSize="xs" color="gray.500" mt={1}>
                                Service ID will be auto-generated from the name
                              </Text>
                            </FormControl>

                            <FormControl isRequired>
                              <FormLabel fontWeight="semibold">Description</FormLabel>
                              <Textarea
                                value={formData.serviceDescription || ""}
                                onChange={(e) => handleInputChange("serviceDescription", e.target.value)}
                                placeholder="Enter service description"
                                bg="white"
                                rows={4}
                              />
                            </FormControl>

                            <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                              <FormControl isRequired>
                                <FormLabel fontWeight="semibold">Model Name</FormLabel>
                                <Select
                                  value={formData.modelId || ""}
                                  onChange={(e) => handleModelNameChange(e.target.value)}
                                  placeholder={isLoadingModels ? "Loading models..." : "Select a model"}
                                  bg="white"
                                  isDisabled={isLoadingModels}
                                >
                                  {modelsForDropdown.map((model) => (
                                    <option key={model.modelId || model.model_id} value={model.modelId || model.model_id}>
                                      {model.name || model.modelId || model.model_id}
                                    </option>
                                  ))}
                                </Select>
                              </FormControl>

                              <FormControl isRequired>
                                <FormLabel fontWeight="semibold">Endpoint</FormLabel>
                                <Input
                                  value={formData.endpoint || ""}
                                  onChange={(e) => handleInputChange("endpoint", e.target.value)}
                                  placeholder="Enter endpoint URL (e.g., http://localhost:8088)"
                                  bg="white"
                                />
                              </FormControl>
                            </SimpleGrid>

                            {/* Auto-populated fields (read-only) */}
                            {formData.modelId && (
                              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                                <FormControl>
                                  <FormLabel fontWeight="semibold">Model ID</FormLabel>
                                  <Input
                                    value={formData.modelId || ""}
                                    isReadOnly
                                    bg="gray.50"
                                    fontSize="sm"
                                  />
                                  <Text fontSize="xs" color="gray.500" mt={1}>
                                    Automatically populated from selected model
                                  </Text>
                                </FormControl>

                                <FormControl>
                                  <FormLabel fontWeight="semibold">Task Type</FormLabel>
                                  <Input
                                    value={formData.task_type || ""}
                                    isReadOnly
                                    bg="gray.50"
                                    fontSize="sm"
                                  />
                                  <Text fontSize="xs" color="gray.500" mt={1}>
                                    Automatically derived from selected model
                                  </Text>
                                </FormControl>
                              </SimpleGrid>
                            )}

                            <HStack justify="flex-end" spacing={4} pt={4}>
                              <Button
                                type="button"
                                variant="outline"
                                onClick={() => {
                                  setFormData({
                                    name: "",
                                    serviceDescription: "",
                                    publishedOn: Math.floor(Date.now() / 1000),
                                    modelId: "",
                                    modelName: "",
                                    endpoint: "",
                                    task_type: "",
                                    modelVersion: "1.0",
                                  });
                                  setPreselectedModelFromQuery(null);
                                }}
                              >
                                Reset
                              </Button>
                              <Button
                                type="submit"
                                colorScheme="blue"
                                isLoading={isSubmitting}
                                loadingText="Creating..."
                              >
                                Create Service
                              </Button>
                            </HStack>
                          </VStack>
                        </form>
                      </CardBody>
                    </Card>
                  </TabPanel>

                  {/* View Service Tab */}
                  {isViewingService && selectedService ? (
                    <TabPanel px={0} pt={6}>
                      <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
                        <CardHeader>
                          <HStack justify="space-between" align="center">
                            <Heading size="md" color="gray.700">
                              Service Details: {selectedService.name || selectedService.serviceId || selectedService.service_id}
                            </Heading>
                            <HStack spacing={2}>
                              {/* Editing disabled for now */}
                              <Button
                                size="sm"
                                colorScheme="red"
                                variant="outline"
                                onClick={() => handleDeleteClick(selectedService)}
                                isLoading={deletingServiceUuid === selectedService.uuid}
                                loadingText="Deleting..."
                                isDisabled={deletingServiceUuid !== null}
                              >
                                Delete Service
                              </Button>
                            </HStack>
                          </HStack>
                        </CardHeader>
                        <CardBody>
                          {!isEditingService && (
                            // View Mode - Display service details
                            <VStack spacing={6} align="stretch">
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
                                    Task Type
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
                                  <Badge
                                    colorScheme={getStatusColor(selectedService.healthStatus?.status || selectedService.status)}
                                    fontSize="sm"
                                    p={2}
                                  >
                                    {(() => {
                                      const status = selectedService.healthStatus?.status || selectedService.status;
                                      // Map status to Publish/Unpublish
                                      if (status === 'active' || status === 'published') {
                                        return 'PUBLISHED';
                                      } else if (status === 'inactive' || status === 'unpublished') {
                                        return 'UNPUBLISHED';
                                      }
                                      return status?.toUpperCase() || "N/A";
                                    })()}
                                  </Badge>
                                  <Text fontSize="xs" color="gray.500" mt={1}>
                                    System-controlled (shown only after creation)
                                  </Text>
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

                              {selectedService.uuid && (
                                <Box>
                                  <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                                    UUID
                                  </Text>
                                  <Text fontSize="sm" fontFamily="mono" color="gray.500">
                                    {selectedService.uuid}
                                  </Text>
                                </Box>
                              )}

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
                          {/* Editing disabled for services after creation - edit form removed */}
                        </CardBody>
                      </Card>
                    </TabPanel>
                  ) : null}
                </TabPanels>
              </Tabs>
            </Card>
          </Grid>
        </VStack>
      </ContentLayout>

      {/* Delete Confirmation Dialog */}
      <AlertDialog
        isOpen={isOpen}
        leastDestructiveRef={cancelRef}
        onClose={onClose}
      >
        <AlertDialogOverlay>
          <AlertDialogContent>
            <AlertDialogHeader fontSize="lg" fontWeight="bold">
              Delete Service
            </AlertDialogHeader>

            <AlertDialogBody>
              Are you sure you want to delete the service{" "}
              <strong>{serviceToDelete?.name || serviceToDelete?.service_id}</strong>? This action
              cannot be undone.
            </AlertDialogBody>

            <AlertDialogFooter>
              <Button ref={cancelRef} onClick={onClose}>
                Cancel
              </Button>
              <Button
                colorScheme="red"
                onClick={handleDeleteConfirm}
                ml={3}
                isLoading={deletingServiceUuid === serviceToDelete?.uuid}
                loadingText="Deleting..."
              >
                Delete
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </>
  );
};

export default ServicesManagementPage;


