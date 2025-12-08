// Model Management page with list and create functionality

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
  Grid
} from "@chakra-ui/react";
import Head from "next/head";
import React, { useState, useEffect } from "react";
import ContentLayout from "../components/common/ContentLayout";
import { unpublishModel, getAllModels, createModel, getModelById, updateModel, publishModel } from "../services/modelManagementService";
import { useAuth } from "../hooks/useAuth";

// TypeScript interfaces for model data
interface OAuthId {
  oauthId: string;
  provider: string;
}

interface TeamMember {
  name: string;
  aboutMe: string;
  oauthId: OAuthId;
}

interface Submitter {
  name: string;
  aboutMe: string;
  team: TeamMember[];
}

interface ModelProcessingType {
  type: string;
}

interface InferenceSchema {
  modelProcessingType: ModelProcessingType;
  request: Record<string, any>;
  response: Record<string, any>;
}

interface InferenceEndPoint {
  schema: InferenceSchema;
}

interface Task {
  type: string;
}

interface Model {
  modelId: string;
  name: string;
  description: string;
  languages: Record<string, any>[];
  domain: string[];
  submitter: Submitter;
  license: string;
  inferenceEndPoint: InferenceEndPoint;
  source: string;
  task: Task;
  isPublished?: boolean;
  version?: string;
  refUrl?: string;
}

// Hardcoded model data
const hardcodedModels: Model[] = [
  {
    modelId: "123456",
    name: "string",
    description: "string",
    languages: [{}],
    domain: ["string"],
    submitter: {
      name: "string",
      aboutMe: "string",
      team: [
        {
          name: "string",
          aboutMe: "string",
          oauthId: {
            oauthId: "string",
            provider: "string",
          },
        },
      ],
    },
    license: "string",
    inferenceEndPoint: {
      schema: {
        modelProcessingType: {
          type: "string",
        },
        request: {},
        response: {},
      },
    },
    source: "string",
    task: {
      type: "asr",
    },
  },
  {
    modelId: "1234567",
    name: "Check name update test",
    description: "string",
    languages: [{}],
    domain: ["string"],
    submitter: {
      name: "string",
      aboutMe: "string",
      team: [
        {
          name: "string",
          aboutMe: "string",
          oauthId: {
            oauthId: "string",
            provider: "string",
          },
        },
      ],
    },
    license: "string",
    inferenceEndPoint: {
      schema: {
        modelProcessingType: {
          type: "string",
        },
        request: {},
        response: {},
      },
    },
    source: "string",
    task: {
      type: "nmt",
    },
  },
  {
    modelId: "12345678",
    name: "string",
    description: "string",
    languages: [{}],
    domain: ["string"],
    submitter: {
      name: "string",
      aboutMe: "string",
      team: [
        {
          name: "string",
          aboutMe: "string",
          oauthId: {
            oauthId: "string",
            provider: "string",
          },
        },
      ],
    },
    license: "string",
    inferenceEndPoint: {
      schema: {
        modelProcessingType: {
          type: "string",
        },
        request: {},
        response: {},
      },
    },
    source: "string",
    task: {
      type: "asr",
    },
  },
  {
    modelId: "A123456789",
    name: "Check name update",
    description: "string",
    languages: [{}],
    domain: ["string"],
    submitter: {
      name: "string",
      aboutMe: "string",
      team: [
        {
          name: "string",
          aboutMe: "string",
          oauthId: {
            oauthId: "string",
            provider: "string",
          },
        },
      ],
    },
    license: "string",
    inferenceEndPoint: {
      schema: {
        modelProcessingType: {
          type: "string",
        },
        request: {},
        response: {},
      },
    },
    source: "string",
    task: {
      type: "nmt",
    },
  },
  {
    modelId: "async_test_1",
    name: "test_update",
    description: "string",
    languages: [{}],
    domain: ["string"],
    submitter: {
      name: "string",
      aboutMe: "string",
      team: [
        {
          name: "string",
          aboutMe: "string",
          oauthId: {
            oauthId: "string",
            provider: "string",
          },
        },
      ],
    },
    license: "string",
    inferenceEndPoint: {
      schema: {
        modelProcessingType: {
          type: "string",
        },
        request: {},
        response: {},
      },
    },
    source: "string",
    task: {
      type: "asr",
    },
  },
  {
    modelId: "ai4bharat/indicasr",
    name: "name_update",
    description: "string",
    languages: [
      {
        additionalProp1: {},
      },
    ],
    domain: ["string"],
    submitter: {
      name: "string",
      aboutMe: "string",
      team: [
        {
          name: "string",
          aboutMe: "string",
          oauthId: {
            oauthId: "string",
            provider: "string",
          },
        },
      ],
    },
    license: "string",
    inferenceEndPoint: {
      schema: {
        modelProcessingType: {
          type: "string",
        },
        request: {},
        response: {},
      },
    },
    source: "string",
    task: {
      type: "string",
    },
  },
  {
    modelId: "ai4bharat/indictrans-v2",
    name: "new_update",
    description: "string",
    languages: [
      {
        additionalProp1: {},
      },
    ],
    domain: ["string"],
    submitter: {
      name: "string",
      aboutMe: "string",
      team: [
        {
          name: "string",
          aboutMe: "string",
          oauthId: {
            oauthId: "string",
            provider: "string",
          },
        },
      ],
    },
    license: "string",
    inferenceEndPoint: {
      schema: {
        modelProcessingType: {
          type: "string",
        },
        request: {},
        response: {},
      },
    },
    source: "string",
    task: {
      type: "string",
    },
  },
];

const ModelManagementPage: React.FC = () => {
  const [models, setModels] = useState<Model[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedModel, setSelectedModel] = useState<Model | null>(null);
  const [isViewingModel, setIsViewingModel] = useState(false);
  const [isEditingModel, setIsEditingModel] = useState(false);
  const [formData, setFormData] = useState<Partial<Model>>({
    name: "",
    description: "",
    modelId: "",
    license: "",
    source: "",
    task: { type: "" },
    domain: [],
    languages: [],
  });
  const [updateFormData, setUpdateFormData] = useState<Partial<Model>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [unpublishingModelId, setUnpublishingModelId] = useState<string | null>(null);
  const [publishingModelId, setPublishingModelId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState(0);
  const toast = useToast();
  const { accessToken } = useAuth();

  // Fetch models on component mount
  useEffect(() => {
    const fetchModels = async () => {
      setIsLoading(true);
      try {
        const fetchedModels = await getAllModels();
        setModels(fetchedModels);
      } catch (error: any) {
        console.error("Failed to fetch models:", error);
        
        // Check if it's an authentication error
        if (error.response?.status === 401) {
          toast({
            title: "Authentication Required",
            description: "Please sign in to view models",
            status: "warning",
            duration: 5000,
            isClosable: true,
          });
          // Don't set hardcoded models on auth error
          setModels([]);
        } else {
          toast({
            title: "Failed to Load Models",
            description: error instanceof Error ? error.message : "Failed to fetch models",
            status: "error",
            duration: 5000,
            isClosable: true,
          });
          // Fallback to hardcoded models on other errors
          setModels(hardcodedModels);
        }
      } finally {
        setIsLoading(false);
      }
    };

    fetchModels();
  }, [toast]);

  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");
  const tableBg = useColorModeValue("white", "gray.800");
  const tableHeaderBg = useColorModeValue("gray.50", "gray.700");

  const getTaskColor = (taskType: string) => {
    switch (taskType.toLowerCase()) {
      case "asr":
        return "orange";
      case "nmt":
        return "green";
      case "tts":
        return "blue";
      default:
        return "gray";
    }
  };

  const handleInputChange = (
    field: keyof Model,
    value: string | Task | string[]
  ) => {
    setFormData((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    try {
      // Prepare model data for API with all required fields
      const currentTimestamp = Math.floor(Date.now() / 1000); // Unix timestamp in seconds
      const modelData: any = {
        modelId: formData.modelId,
        version: "1.0", // Default version
        submittedOn: currentTimestamp,
        updatedOn: currentTimestamp,
        name: formData.name,
        description: formData.description,
        refUrl: formData.source || "string", // Use source as refUrl if available
        task: formData.task || { type: "" },
        license: formData.license || "string",
        source: formData.source || "string",
        domain: formData.domain || ["string"],
        languages: formData.languages || [{}],
        benchmarks: [], // Empty benchmarks array (required field)
        submitter: {
          name: "string",
          aboutMe: "string",
          team: [
            {
              name: "string",
              aboutMe: "string",
              oauthId: {
                oauthId: "string",
                provider: "string",
              },
            },
          ],
        },
        inferenceEndPoint: {
          schema: {
            modelProcessingType: {
              type: "string",
            },
            request: {},
            response: {},
          },
        },
      };

      const createdModel = await createModel(modelData);

      toast({
        title: "Model Created",
        description: "Model has been created successfully",
        status: "success",
        duration: 3000,
        isClosable: true,
      });

      // Refresh models list
      const fetchedModels = await getAllModels();
      setModels(fetchedModels);

      // Reset form
      setFormData({
        name: "",
        description: "",
        modelId: "",
        license: "",
        source: "",
        task: { type: "" },
        domain: [],
        languages: [],
      });
    } catch (error) {
      toast({
        title: "Creation Failed",
        description: error instanceof Error ? error.message : "Failed to create model",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleViewModel = async (modelId: string) => {
    try {
      const model = await getModelById(modelId);
      setSelectedModel(model);
      // Ensure task field is properly initialized
      setUpdateFormData({
        ...model,
        task: model.task || { type: "" },
      });
      setIsViewingModel(true);
      setActiveTab(2); // Switch to View Model tab
    } catch (error) {
      toast({
        title: "Failed to Load Model",
        description: error instanceof Error ? error.message : "Failed to fetch model details",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    }
  };

  const handleUpdateModel = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedModel) return;

    setIsUpdating(true);
    try {
      const updateData: any = {
        modelId: selectedModel.modelId,
        name: updateFormData.name,
        description: updateFormData.description,
        task: updateFormData.task,
        license: updateFormData.license,
        source: updateFormData.source,
        domain: updateFormData.domain || [],
        languages: updateFormData.languages || [],
      };

      await updateModel(updateData);

      toast({
        title: "Model Updated",
        description: "Model has been updated successfully",
        status: "success",
        duration: 3000,
        isClosable: true,
      });

      // Refresh models list and selected model
      const fetchedModels = await getAllModels();
      setModels(fetchedModels);
      const updatedModel = await getModelById(selectedModel.modelId);
      setSelectedModel(updatedModel);
      setUpdateFormData(updatedModel);
      setIsEditingModel(false);
    } catch (error) {
      toast({
        title: "Update Failed",
        description: error instanceof Error ? error.message : "Failed to update model",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsUpdating(false);
    }
  };

  const handlePublish = async (modelId: string) => {
    setPublishingModelId(modelId);
    
    try {
      await publishModel(modelId);
      
      // Refresh models list and selected model
      const fetchedModels = await getAllModels();
      setModels(fetchedModels);
      if (selectedModel && selectedModel.modelId === modelId) {
        const updatedModel = await getModelById(modelId);
        setSelectedModel(updatedModel);
        setUpdateFormData(updatedModel);
      }

      toast({
        title: "Model Published",
        description: `Model ${modelId} has been published successfully`,
        status: "success",
        duration: 3000,
        isClosable: true,
      });
    } catch (error) {
      toast({
        title: "Publish Failed",
        description: error instanceof Error ? error.message : "Failed to publish model",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setPublishingModelId(null);
    }
  };

  const handleUnpublish = async (modelId: string) => {
    setUnpublishingModelId(modelId);
    
    try {
      // Call the unpublish API
      const response = await unpublishModel(modelId);
      
      // Refresh models list from API
      const fetchedModels = await getAllModels();
      setModels(fetchedModels);
      
      // Update selected model if it's the one being unpublished
      if (selectedModel && selectedModel.modelId === modelId) {
        const updatedModel = await getModelById(modelId);
        setSelectedModel(updatedModel);
        setUpdateFormData(updatedModel);
      }

      toast({
        title: "Model Unpublished",
        description: response.message || `Model ${modelId} has been unpublished successfully`,
        status: "success",
        duration: 3000,
        isClosable: true,
      });
    } catch (error) {
      toast({
        title: "Unpublish Failed",
        description: error instanceof Error ? error.message : "Failed to unpublish model",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setUnpublishingModelId(null);
    }
  };

  return (
    <>
      <Head>
        <title>Model Management - AI4I Platform</title>
        <meta name="description" content="Manage and configure AI models" />
      </Head>

      <ContentLayout>
           <VStack spacing={6} w="full">
                  {/* Page Header */}
                  <Box textAlign="center" mb={2}>
                    <Heading size="lg" color="gray.800" mb={1}>
                     Model Management
                    </Heading>
                    <Text color="gray.600" fontSize="sm">
                    Manage and configure AI models
                    </Text>
                  </Box>
        
                  <Grid
                    gap={8}
                    w="full"
                  
                    mx="auto"
                  > <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px">
            <Tabs 
              colorScheme="blue" 
              variant="enclosed" 
              index={activeTab}
              onChange={(index) => {
                setActiveTab(index);
                if (index !== 2) {
                  setIsViewingModel(false);
                  setSelectedModel(null);
                }
              }}
            >
              <TabList>
                <Tab fontWeight="semibold">List Models</Tab>
                <Tab fontWeight="semibold">Create Model</Tab>
                {isViewingModel && (
                  <Tab fontWeight="semibold">View Model</Tab>
                )}
              </TabList>

              <TabPanels>
                {/* List Models Tab */}
                <TabPanel px={0} pt={6}>
                  <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
                    <CardHeader>
                      <Heading size="md" color="gray.700">
                        All Models
                      </Heading>
                    </CardHeader>
                    <CardBody>
                      {isLoading ? (
                        <Box textAlign="center" py={8}>
                          <Text color="gray.500">Loading models...</Text>
                        </Box>
                      ) : (
                        <Box overflowX="auto">
                          <Table variant="simple" bg={tableBg}>
                            <Thead bg={tableHeaderBg}>
                              <Tr>
                                <Th>Model ID</Th>
                                <Th>Name</Th>
                                <Th>Description</Th>
                                <Th>Task Type</Th>
                                <Th>License</Th>
                                <Th>Source</Th>
                                <Th>Domain</Th>
                                <Th>Actions</Th>
                              </Tr>
                            </Thead>
                            <Tbody>
                              {models.map((model) => (
                              <Tr 
                                key={model.modelId} 
                                _hover={{ bg: useColorModeValue("gray.50", "gray.700"), cursor: "pointer" }}
                                onClick={() => handleViewModel(model.modelId)}
                              >
                                <Td>
                                  <Text fontWeight="medium" fontSize="sm">
                                    {model.modelId}
                                  </Text>
                                </Td>
                                <Td>
                                  <Text fontSize="sm">{model.name}</Text>
                                </Td>
                                <Td>
                                  <Text fontSize="sm" noOfLines={2} maxW="300px">
                                    {model.description}
                                  </Text>
                                </Td>
                                <Td>
                                  <Badge
                                    colorScheme={getTaskColor(model.task.type)}
                                    fontSize="xs"
                                  >
                                    {model.task.type.toUpperCase()}
                                  </Badge>
                                </Td>
                                <Td>
                                  <Text fontSize="sm">{model.license}</Text>
                                </Td>
                                <Td>
                                  <Text fontSize="sm" noOfLines={1} maxW="200px">
                                    {model.source}
                                  </Text>
                                </Td>
                                <Td>
                                  <HStack spacing={1} flexWrap="wrap">
                                    {model.domain.slice(0, 2).map((domain, idx) => (
                                      <Badge key={idx} fontSize="xs" colorScheme="gray">
                                        {domain}
                                      </Badge>
                                    ))}
                                    {model.domain.length > 2 && (
                                      <Badge fontSize="xs" colorScheme="gray">
                                        +{model.domain.length - 2}
                                      </Badge>
                                    )}
                                  </HStack>
                                </Td>
                                <Td onClick={(e) => e.stopPropagation()}>
                                  <HStack spacing={2}>
                                    <Button
                                      size="sm"
                                      colorScheme="blue"
                                      variant="outline"
                                      onClick={() => handleViewModel(model.modelId)}
                                    >
                                      View
                                    </Button>
                                    {model.isPublished === true ? (
                                      <Button
                                        size="sm"
                                        colorScheme="red"
                                        variant="outline"
                                        onClick={() => handleUnpublish(model.modelId)}
                                        isLoading={unpublishingModelId === model.modelId}
                                        loadingText="Unpublishing..."
                                        isDisabled={unpublishingModelId !== null || publishingModelId !== null}
                                      >
                                        Unpublish
                                      </Button>
                                    ) : (
                                      <Button
                                        size="sm"
                                        colorScheme="green"
                                        variant="outline"
                                        onClick={() => handlePublish(model.modelId)}
                                        isLoading={publishingModelId === model.modelId}
                                        loadingText="Publishing..."
                                        isDisabled={unpublishingModelId !== null || publishingModelId !== null}
                                      >
                                        Publish
                                      </Button>
                                    )}
                                  </HStack>
                                </Td>
                              </Tr>
                              ))}
                            </Tbody>
                          </Table>
                        </Box>
                      )}
                      {!isLoading && models.length === 0 && (
                        <Box textAlign="center" py={8}>
                          <Text color="gray.500">No models found</Text>
                        </Box>
                      )}
                    </CardBody>
                  </Card>
                </TabPanel>

                {/* Create Model Tab */}
                <TabPanel px={0} pt={6}>
                  <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
                    <CardHeader>
                      <Heading size="md" color="gray.700">
                        Create New Model
                      </Heading>
                    </CardHeader>
                    <CardBody>
                      <form onSubmit={handleSubmit}>
                        <VStack spacing={6} align="stretch">
                          <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                            <FormControl isRequired>
                              <FormLabel fontWeight="semibold">Model ID</FormLabel>
                              <Input
                                value={formData.modelId || ""}
                                onChange={(e) => handleInputChange("modelId", e.target.value)}
                                placeholder="Enter model ID"
                                bg="white"
                              />
                            </FormControl>

                            <FormControl isRequired>
                              <FormLabel fontWeight="semibold">Name</FormLabel>
                              <Input
                                value={formData.name || ""}
                                onChange={(e) => handleInputChange("name", e.target.value)}
                                placeholder="Enter model name"
                                bg="white"
                              />
                            </FormControl>
                          </SimpleGrid>

                          <FormControl isRequired>
                            <FormLabel fontWeight="semibold">Description</FormLabel>
                            <Textarea
                              value={formData.description || ""}
                              onChange={(e) => handleInputChange("description", e.target.value)}
                              placeholder="Enter model description"
                              bg="white"
                              rows={4}
                            />
                          </FormControl>

                          <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                            <FormControl isRequired>
                              <FormLabel fontWeight="semibold">Task Type</FormLabel>
                              <Select
                                value={formData.task?.type || ""}
                                onChange={(e) =>
                                  handleInputChange("task", { type: e.target.value })
                                }
                                placeholder="Select task type"
                                bg="white"
                              >
                                <option value="asr">ASR (Automatic Speech Recognition)</option>
                                <option value="tts">TTS (Text-to-Speech)</option>
                                <option value="nmt">NMT (Neural Machine Translation)</option>
                                <option value="llm">LLM (Large Language Model)</option>
                              </Select>
                            </FormControl>

                            <FormControl>
                              <FormLabel fontWeight="semibold">License</FormLabel>
                              <Input
                                value={formData.license || ""}
                                onChange={(e) => handleInputChange("license", e.target.value)}
                                placeholder="Enter license"
                                bg="white"
                              />
                            </FormControl>
                          </SimpleGrid>

                          <FormControl>
                            <FormLabel fontWeight="semibold">Source</FormLabel>
                            <Input
                              value={formData.source || ""}
                              onChange={(e) => handleInputChange("source", e.target.value)}
                              placeholder="Enter source URL or repository"
                              bg="white"
                            />
                          </FormControl>

                          <HStack justify="flex-end" spacing={4} pt={4}>
                            <Button
                              type="button"
                              variant="outline"
                              onClick={() => {
                                setFormData({
                                  name: "",
                                  description: "",
                                  modelId: "",
                                  license: "",
                                  source: "",
                                  task: { type: "" },
                                  domain: [],
                                  languages: [],
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
                              Create Model
                            </Button>
                          </HStack>
                        </VStack>
                      </form>
                    </CardBody>
                  </Card>
                </TabPanel>

                {/* View Model Tab */}
                {isViewingModel && selectedModel && (
                  <TabPanel px={0} pt={6}>
                    <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
                      <CardHeader>
                        <HStack justify="space-between" align="center">
                          <Heading size="md" color="gray.700">
                            Model Details: {selectedModel.name}
                          </Heading>
                          <HStack spacing={2}>
                            {selectedModel.isPublished !== true && (
                              <Button
                                size="sm"
                                colorScheme="green"
                                onClick={() => handlePublish(selectedModel.modelId)}
                                isLoading={publishingModelId === selectedModel.modelId}
                                loadingText="Publishing..."
                                isDisabled={publishingModelId !== null || unpublishingModelId !== null}
                              >
                                Publish Model
                              </Button>
                            )}
                            {selectedModel.isPublished === true && (
                              <Button
                                size="sm"
                                colorScheme="red"
                                variant="outline"
                                onClick={() => handleUnpublish(selectedModel.modelId)}
                                isLoading={unpublishingModelId === selectedModel.modelId}
                                loadingText="Unpublishing..."
                                isDisabled={publishingModelId !== null || unpublishingModelId !== null}
                              >
                                Unpublish Model
                              </Button>
                            )}
                            {!isEditingModel ? (
                              <Button
                                size="sm"
                                colorScheme="blue"
                                onClick={() => setIsEditingModel(true)}
                              >
                                Edit Model
                              </Button>
                            ) : (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => {
                                  setIsEditingModel(false);
                                  setUpdateFormData({
                                    ...selectedModel,
                                    task: selectedModel.task || { type: "" },
                                  });
                                }}
                              >
                                Cancel
                              </Button>
                            )}
                          </HStack>
                        </HStack>
                      </CardHeader>
                      <CardBody>
                        {!isEditingModel ? (
                          // View Mode - Display model details
                          <VStack spacing={6} align="stretch">
                            <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                              <Box>
                                <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                                  Model ID
                                </Text>
                                <Text fontSize="md">{selectedModel.modelId}</Text>
                              </Box>
                              <Box>
                                <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                                  Name
                                </Text>
                                <Text fontSize="md">{selectedModel.name}</Text>
                              </Box>
                            </SimpleGrid>

                            <Box>
                              <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                                Description
                              </Text>
                              <Text fontSize="md">{selectedModel.description}</Text>
                            </Box>

                            <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                              <Box>
                                <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                                  Task Type
                                </Text>
                                <Badge
                                  colorScheme={getTaskColor(selectedModel.task.type)}
                                  fontSize="sm"
                                  p={2}
                                >
                                  {selectedModel.task.type.toUpperCase()}
                                </Badge>
                              </Box>
                              <Box>
                                <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                                  Status
                                </Text>
                                <Badge
                                  colorScheme={selectedModel.isPublished === true ? "green" : "red"}
                                  fontSize="sm"
                                  p={2}
                                >
                                  {selectedModel.isPublished === true ? "Published" : "Unpublished"}
                                </Badge>
                              </Box>
                            </SimpleGrid>

                            <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                              <Box>
                                <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                                  License
                                </Text>
                                <Text fontSize="md">{selectedModel.license}</Text>
                              </Box>
                              <Box>
                                <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                                  Source
                                </Text>
                                <Text fontSize="md">{selectedModel.source}</Text>
                              </Box>
                            </SimpleGrid>

                            <Box>
                              <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={2}>
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
                                  <Text color="gray.500" fontSize="sm">No domains specified</Text>
                                )}
                              </HStack>
                            </Box>

                            {selectedModel.version && (
                              <Box>
                                <Text fontWeight="bold" color="gray.600" fontSize="sm" mb={1}>
                                  Version
                                </Text>
                                <Text fontSize="md">{selectedModel.version}</Text>
                              </Box>
                            )}
                          </VStack>
                        ) : (
                          // Edit Mode - Update form
                          <form onSubmit={handleUpdateModel}>
                            <VStack spacing={6} align="stretch">
                              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                                <FormControl>
                                  <FormLabel fontWeight="semibold">Model ID</FormLabel>
                                  <Input
                                    value={selectedModel.modelId}
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
                                    placeholder="Enter model name"
                                    bg="white"
                                  />
                                </FormControl>
                              </SimpleGrid>

                              <FormControl isRequired>
                                <FormLabel fontWeight="semibold">Description</FormLabel>
                                <Textarea
                                  value={updateFormData.description || ""}
                                  onChange={(e) =>
                                    setUpdateFormData((prev) => ({
                                      ...prev,
                                      description: e.target.value,
                                    }))
                                  }
                                  placeholder="Enter model description"
                                  bg="white"
                                  rows={4}
                                />
                              </FormControl>

                              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                                <FormControl isRequired>
                                  <FormLabel fontWeight="semibold">Task Type</FormLabel>
                                  <Select
                                    value={updateFormData.task?.type || selectedModel?.task?.type || ""}
                                    onChange={(e) =>
                                      setUpdateFormData((prev) => ({
                                        ...prev,
                                        task: { type: e.target.value },
                                      }))
                                    }
                                    placeholder="Select task type"
                                    bg="white"
                                  >
                                    <option value="asr">ASR (Automatic Speech Recognition)</option>
                                    <option value="tts">TTS (Text-to-Speech)</option>
                                    <option value="nmt">NMT (Neural Machine Translation)</option>
                                    <option value="llm">LLM (Large Language Model)</option>
                                  </Select>
                                </FormControl>

                                <FormControl>
                                  <FormLabel fontWeight="semibold">License</FormLabel>
                                  <Input
                                    value={updateFormData.license || ""}
                                    onChange={(e) =>
                                      setUpdateFormData((prev) => ({
                                        ...prev,
                                        license: e.target.value,
                                      }))
                                    }
                                    placeholder="Enter license"
                                    bg="white"
                                  />
                                </FormControl>
                              </SimpleGrid>

                              <FormControl>
                                <FormLabel fontWeight="semibold">Source</FormLabel>
                                <Input
                                  value={updateFormData.source || ""}
                                  onChange={(e) =>
                                    setUpdateFormData((prev) => ({
                                      ...prev,
                                      source: e.target.value,
                                    }))
                                  }
                                  placeholder="Enter source URL or repository"
                                  bg="white"
                                />
                              </FormControl>

                              <HStack justify="flex-end" spacing={4} pt={4}>
                                <Button
                                  type="submit"
                                  colorScheme="blue"
                                  isLoading={isUpdating}
                                  loadingText="Updating..."
                                >
                                  Update Model
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
          </Card></Grid>
     </VStack>
      </ContentLayout>
    </>
  );
};

export default ModelManagementPage;

