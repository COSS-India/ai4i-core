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

const ServicesManagementPage: React.FC = () => {
  const [services, setServices] = useState<Service[]>([]);
  const [models, setModels] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingModels, setIsLoadingModels] = useState(false);
  const [selectedService, setSelectedService] = useState<Service | null>(null);
  const [isViewingService, setIsViewingService] = useState(false);
  const [isEditingService, setIsEditingService] = useState(false);
  const [formData, setFormData] = useState<Partial<Service>>({
    serviceId: "",
    name: "",
    serviceDescription: "",
    hardwareDescription: "",
    publishedOn: Math.floor(Date.now() / 1000),
    modelId: "",
    endpoint: "",
    api_key: "",
    task_type: "",
    status: "active",
  });
  const [updateFormData, setUpdateFormData] = useState<Partial<Service>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [deletingServiceUuid, setDeletingServiceUuid] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState(0);
  const toast = useToast();
  const { accessToken } = useAuth();
  const { checkSessionExpiry } = useSessionExpiry();
  const { isOpen, onOpen, onClose } = useDisclosure();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const [serviceToDelete, setServiceToDelete] = useState<Service | null>(null);

  // Fetch services on component mount
  useEffect(() => {
    const fetchServices = async () => {
      setIsLoading(true);
      try {
        const fetchedServices = await listServices();
        setServices(fetchedServices);
      } catch (error: any) {
        console.error("Failed to fetch services:", error);
        
        // Check if it's an authentication error
        if (error.response?.status === 401 || error.message?.includes('Authentication') || error.message?.includes('401')) {
          const errorMessage = error instanceof Error ? error.message : "Authentication failed";
          toast({
            title: "Authentication Error",
            description: errorMessage.includes('Services management') ? errorMessage : `Services management error: ${errorMessage}. Please check your login status and try again.`,
            status: "error",
            duration: 5000,
            isClosable: true,
          });
          setServices([]);
        } else {
          toast({
            title: "Failed to Load Services",
            description: error instanceof Error ? error.message : "Failed to fetch services",
            status: "error",
            duration: 5000,
            isClosable: true,
          });
          setServices([]);
        }
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
        setModels(fetchedModels);
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

  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");
  const tableBg = useColorModeValue("white", "gray.800");
  const tableHeaderBg = useColorModeValue("gray.50", "gray.700");
  const tableRowHoverBg = useColorModeValue("gray.50", "gray.700");

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

  // Handle model selection and derive task_type
  const handleModelChange = async (modelId: string) => {
    // Check session expiry before fetching model details
    if (!checkSessionExpiry()) return;
    
    setFormData((prev) => ({
      ...prev,
      modelId: modelId,
    }));

    if (modelId) {
      try {
        setIsLoadingModels(true);
        const modelDetails = await getModelById(modelId);
        
        // Extract task_type from model
        // The task_type might be in model.task.type or model.task_type
        const taskType = modelDetails?.task?.type || modelDetails?.task_type || modelDetails?.taskType || "";
        
        if (taskType) {
          setFormData((prev) => ({
            ...prev,
            modelId: modelId,
            task_type: taskType,
          }));
        }
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
      // Clear task_type if no model selected
      setFormData((prev) => ({
        ...prev,
        task_type: "",
      }));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Check session expiry before submitting
    if (!checkSessionExpiry()) return;
    
    setIsSubmitting(true);

    try {
      const createdService = await createService(formData);

      toast({
        title: "Service Created",
        description: "Service has been created successfully",
        status: "success",
        duration: 3000,
        isClosable: true,
      });

      // Reset form
      setFormData({
        serviceId: "",
        name: "",
        serviceDescription: "",
        hardwareDescription: "",
        publishedOn: Math.floor(Date.now() / 1000),
        modelId: "",
        endpoint: "",
        api_key: "",
        task_type: "",
        status: "active",
      });

      // Refresh services list
      const fetchedServices = await listServices();
      setServices(fetchedServices);

      // Switch to list tab
      setActiveTab(0);
    } catch (error: any) {
      const errorMessage = error instanceof Error ? error.message : "Failed to create service";
      toast({
        title: "Create Failed",
        description: errorMessage,
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
      toast({
        title: "View Failed",
        description: errorMessage,
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
      toast({
        title: "Update Failed",
        description: errorMessage,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsUpdating(false);
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
      toast({
        title: "Delete Failed",
        description: errorMessage,
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
                                        colorScheme={getStatusColor(service.healthStatus?.status || service.status)}
                                        fontSize="sm"
                                        p={1}
                                      >
                                        {(service.healthStatus?.status || service.status)?.toUpperCase() || "N/A"}
                                      </Badge>
                                    </Td>
                                    <Td>
                                      <HStack spacing={2}>
                                        <Button
                                          size="sm"
                                          colorScheme="blue"
                                          variant="outline"
                                          onClick={() => handleViewService(service.serviceId || service.service_id || "")}
                                        >
                                          View
                                        </Button>
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
                            <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                              <FormControl isRequired>
                                <FormLabel fontWeight="semibold">Service ID</FormLabel>
                                <Input
                                  value={formData.serviceId || ""}
                                  onChange={(e) => handleInputChange("serviceId", e.target.value)}
                                  placeholder="Enter service ID"
                                  bg="white"
                                />
                              </FormControl>

                              <FormControl isRequired>
                                <FormLabel fontWeight="semibold">Name</FormLabel>
                                <Input
                                  value={formData.name || ""}
                                  onChange={(e) => handleInputChange("name", e.target.value)}
                                  placeholder="Enter service name"
                                  bg="white"
                                />
                              </FormControl>
                            </SimpleGrid>

                            <FormControl isRequired>
                              <FormLabel fontWeight="semibold">Service Description</FormLabel>
                              <Textarea
                                value={formData.serviceDescription || ""}
                                onChange={(e) => handleInputChange("serviceDescription", e.target.value)}
                                placeholder="Enter service description"
                                bg="white"
                                rows={4}
                              />
                            </FormControl>

                            <FormControl isRequired>
                              <FormLabel fontWeight="semibold">Hardware Description</FormLabel>
                              <Input
                                value={formData.hardwareDescription || ""}
                                onChange={(e) => handleInputChange("hardwareDescription", e.target.value)}
                                placeholder="Enter hardware description"
                                bg="white"
                              />
                            </FormControl>

                            <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                              <FormControl>
                                <FormLabel fontWeight="semibold">Task Type</FormLabel>
                                <Input
                                  value={formData.task_type || ""}
                                  isReadOnly
                                  bg="gray.50"
                                  placeholder="Will be derived from selected model"
                                  fontSize="sm"
                                />
                                <Text fontSize="xs" color="gray.500" mt={1}>
                                  Automatically set when you select a model
                                </Text>
                              </FormControl>

                              <FormControl>
                                <FormLabel fontWeight="semibold">Status</FormLabel>
                                <Select
                                  value={formData.status || "active"}
                                  onChange={(e) => handleInputChange("status", e.target.value)}
                                  bg="white"
                                >
                                  <option value="active">Active</option>
                                  <option value="inactive">Inactive</option>
                                  <option value="pending">Pending</option>
                                </Select>
                              </FormControl>
                            </SimpleGrid>

                            <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                              <FormControl isRequired>
                                <FormLabel fontWeight="semibold">Model ID</FormLabel>
                                <Select
                                  value={formData.modelId || ""}
                                  onChange={(e) => handleModelChange(e.target.value)}
                                  placeholder={isLoadingModels ? "Loading models..." : "Select a model"}
                                  bg="white"
                                  isDisabled={isLoadingModels}
                                >
                                  {models.map((model) => (
                                    <option key={model.modelId || model.model_id} value={model.modelId || model.model_id}>
                                      {model.name || model.modelId || model.model_id}
                                    </option>
                                  ))}
                                </Select>
                                {formData.modelId && formData.task_type && (
                                  <Text fontSize="xs" color="blue.500" mt={1}>
                                    Task Type: {formData.task_type.toUpperCase()} (derived from model)
                                  </Text>
                                )}
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

                            <FormControl isRequired>
                              <FormLabel fontWeight="semibold">API Key</FormLabel>
                              <Input
                                value={formData.api_key || ""}
                                onChange={(e) => handleInputChange("api_key", e.target.value)}
                                placeholder="Enter API key for the service"
                                bg="white"
                                type="password"
                              />
                            </FormControl>

                            <HStack justify="flex-end" spacing={4} pt={4}>
                              <Button
                                type="button"
                                variant="outline"
                                onClick={() => {
                                  setFormData({
                                    serviceId: "",
                                    name: "",
                                    serviceDescription: "",
                                    hardwareDescription: "",
                                    publishedOn: Math.floor(Date.now() / 1000),
                                    modelId: "",
                                    endpoint: "",
                                    api_key: "",
                                    task_type: "",
                                    status: "active",
                                  });
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
                  {isViewingService && selectedService && (
                    <TabPanel px={0} pt={6}>
                      <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
                        <CardHeader>
                          <HStack justify="space-between" align="center">
                            <Heading size="md" color="gray.700">
                              Service Details: {selectedService.name || selectedService.serviceId || selectedService.service_id}
                            </Heading>
                            <HStack spacing={2}>
                              {!isEditingService ? (
                                <>
                                  <Button
                                    size="sm"
                                    colorScheme="blue"
                                    onClick={() => setIsEditingService(true)}
                                  >
                                    Edit Service
                                  </Button>
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
                                </>
                              ) : (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() => {
                                    setIsEditingService(false);
                                    setUpdateFormData(selectedService);
                                  }}
                                >
                                  Cancel
                                </Button>
                              )}
                            </HStack>
                          </HStack>
                        </CardHeader>
                        <CardBody>
                          {!isEditingService ? (
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
                                    Status
                                  </Text>
                                  <Badge
                                    colorScheme={getStatusColor(selectedService.healthStatus?.status || selectedService.status)}
                                    fontSize="sm"
                                    p={2}
                                  >
                                    {(selectedService.healthStatus?.status || selectedService.status)?.toUpperCase() || "N/A"}
                                  </Badge>
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
                          ) : (
                            // Edit Mode - Update form
                            <form onSubmit={handleUpdateService}>
                              <VStack spacing={6} align="stretch">
                                <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                                  <FormControl>
                                    <FormLabel fontWeight="semibold">Service ID</FormLabel>
                                    <Input
                                      value={updateFormData.serviceId || updateFormData.service_id || ""}
                                      isDisabled
                                      bg="gray.50"
                                      fontSize="sm"
                                    />
                                  </FormControl>
                                  <FormControl isRequired>
                                    <FormLabel fontWeight="semibold">Name</FormLabel>
                                    <Input
                                      value={updateFormData.name || ""}
                                      onChange={(e) =>
                                        setUpdateFormData((prev) => ({ ...prev, name: e.target.value }))
                                      }
                                      placeholder="Enter service name"
                                      bg="white"
                                    />
                                  </FormControl>
                                </SimpleGrid>

                                <FormControl isRequired>
                                  <FormLabel fontWeight="semibold">Service Description</FormLabel>
                                  <Textarea
                                    value={updateFormData.serviceDescription || updateFormData.description || ""}
                                    onChange={(e) =>
                                      setUpdateFormData((prev) => ({
                                        ...prev,
                                        serviceDescription: e.target.value,
                                        description: e.target.value, // Keep for backward compatibility
                                      }))
                                    }
                                    placeholder="Enter service description"
                                    bg="white"
                                    rows={4}
                                  />
                                </FormControl>

                                <FormControl isRequired>
                                  <FormLabel fontWeight="semibold">Hardware Description</FormLabel>
                                  <Input
                                    value={updateFormData.hardwareDescription || ""}
                                    onChange={(e) =>
                                      setUpdateFormData((prev) => ({
                                        ...prev,
                                        hardwareDescription: e.target.value,
                                      }))
                                    }
                                    placeholder="Enter hardware description"
                                    bg="white"
                                  />
                                </FormControl>

                                <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                                  <FormControl>
                                    <FormLabel fontWeight="semibold">Task Type</FormLabel>
                                    <Input
                                      value={updateFormData.task_type || ""}
                                      isReadOnly
                                      bg="gray.50"
                                      placeholder="Will be derived from selected model"
                                      fontSize="sm"
                                    />
                                    <Text fontSize="xs" color="gray.500" mt={1}>
                                      Automatically set when you select a model
                                    </Text>
                                  </FormControl>

                                  <FormControl>
                                    <FormLabel fontWeight="semibold">Status</FormLabel>
                                    <Select
                                      value={updateFormData.status || "active"}
                                      onChange={(e) =>
                                        setUpdateFormData((prev) => ({
                                          ...prev,
                                          status: e.target.value,
                                        }))
                                      }
                                      bg="white"
                                    >
                                      <option value="active">Active</option>
                                      <option value="inactive">Inactive</option>
                                      <option value="pending">Pending</option>
                                    </Select>
                                  </FormControl>
                                </SimpleGrid>

                                <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                                  <FormControl isRequired>
                                    <FormLabel fontWeight="semibold">Model ID</FormLabel>
                                    <Select
                                      value={updateFormData.modelId || updateFormData.model_id || ""}
                                      onChange={async (e) => {
                                        const modelId = e.target.value;
                                        setUpdateFormData((prev) => ({
                                          ...prev,
                                          modelId: modelId,
                                          model_id: modelId, // Keep for backward compatibility
                                        }));

                                        // Fetch model details and derive task_type
                                        if (modelId) {
                                          try {
                                            const modelDetails = await getModelById(modelId);
                                            const taskType = modelDetails?.task?.type || modelDetails?.task_type || modelDetails?.taskType || "";
                                            if (taskType) {
                                              setUpdateFormData((prev) => ({
                                                ...prev,
                                                task_type: taskType,
                                              }));
                                            }
                                          } catch (error: any) {
                                            console.error("Failed to fetch model details:", error);
                                          }
                                        }
                                      }}
                                      placeholder={isLoadingModels ? "Loading models..." : "Select a model"}
                                      bg="white"
                                      isDisabled={isLoadingModels}
                                    >
                                      {models.map((model) => (
                                        <option key={model.modelId || model.model_id} value={model.modelId || model.model_id}>
                                          {model.name || model.modelId || model.model_id}
                                        </option>
                                      ))}
                                    </Select>
                                    {updateFormData.modelId && updateFormData.task_type && (
                                      <Text fontSize="xs" color="blue.500" mt={1}>
                                        Task Type: {updateFormData.task_type.toUpperCase()} (derived from model)
                                      </Text>
                                    )}
                                  </FormControl>

                                  <FormControl isRequired>
                                    <FormLabel fontWeight="semibold">Endpoint</FormLabel>
                                    <Input
                                      value={updateFormData.endpoint || updateFormData.endpoint_url || ""}
                                      onChange={(e) =>
                                        setUpdateFormData((prev) => ({
                                          ...prev,
                                          endpoint: e.target.value,
                                          endpoint_url: e.target.value, // Keep for backward compatibility
                                        }))
                                      }
                                      placeholder="Enter endpoint URL"
                                      bg="white"
                                    />
                                  </FormControl>
                                </SimpleGrid>

                                <FormControl isRequired>
                                  <FormLabel fontWeight="semibold">API Key</FormLabel>
                                  <Input
                                    value={updateFormData.api_key || updateFormData.apiKey || ""}
                                    onChange={(e) =>
                                      setUpdateFormData((prev) => ({
                                        ...prev,
                                        api_key: e.target.value,
                                        apiKey: e.target.value, // Keep for backward compatibility
                                      }))
                                    }
                                    placeholder="Enter API key"
                                    bg="white"
                                    type="password"
                                  />
                                </FormControl>

                                <HStack justify="flex-end" spacing={4} pt={4}>
                                  <Button
                                    type="submit"
                                    colorScheme="blue"
                                    isLoading={isUpdating}
                                    loadingText="Updating..."
                                  >
                                    Update Service
                                  </Button>
                                </HStack>
                              </VStack>
                            </form>
                          )}
                        </CardBody>
                      </Card>
                    </TabPanel>
                  )}
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


