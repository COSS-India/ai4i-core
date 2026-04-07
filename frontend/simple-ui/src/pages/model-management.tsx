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
  IconButton,
  Input,
  InputGroup,
  InputLeftElement,
  Select,
  Switch,
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
  useDisclosure,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
  useToast,
  Textarea,
  SimpleGrid,
  Grid,
  Alert,
  AlertIcon,
  AlertDescription,
  Code,
  Spinner,
  Center,
  Tooltip,
} from "@chakra-ui/react";
import Head from "next/head";
import { SearchIcon, ViewIcon } from "@chakra-ui/icons";
import { useRouter } from "next/router";
import React, { useState, useEffect, useRef, useMemo } from "react";
import ContentLayout from "../components/common/ContentLayout";
import { getAllModels, createModel, getModelById, updateModel } from "../services/modelManagementService";
import { listServices as listServicesForModels } from "../services/servicesManagementService";
import { useAuth } from "../hooks/useAuth";
import { useSessionExpiry } from "../hooks/useSessionExpiry";
import { extractErrorInfo } from "../utils/errorHandler";
import { useToastWithDeduplication } from "../hooks/useToastWithDeduplication";
import ConfirmDialog from "../components/common/ConfirmDialog";
import { TableFilterToolbar, TablePaginationBar, TableSortHeader } from "../components/common/TableControls";

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
  version?: string;
  versionStatus?: "active" | "deprecated" | "ACTIVE" | "DEPRECATED";
  refUrl?: string;
  /** ISO timestamp when version status was last updated; used for list ordering */
  versionStatusUpdatedAt?: string;
  /** Epoch (seconds or ms) when model was created; fallback for ordering */
  submittedOn?: number;
  /** Epoch (seconds or ms) when model was last updated; fallback for ordering */
  updatedOn?: number;
}

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
  const [activeTab, setActiveTab] = useState(0);
  const [listPage, setListPage] = useState(1);
  const [listPageSize, setListPageSize] = useState(25);
  const [uploadedModelData, setUploadedModelData] = useState<any>(null);
  const [parsedModelData, setParsedModelData] = useState<any>(null);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [updatingModelId, setUpdatingModelId] = useState<string | null>(null);
  /** Model IDs that have at least one published service; deprecate is disabled for these until all are unpublished */
  const [modelIdsWithPublishedService, setModelIdsWithPublishedService] = useState<Set<string>>(new Set());
  const [modelToConfirm, setModelToConfirm] = useState<Model | null>(null);
  const [confirmAction, setConfirmAction] = useState<"deprecate" | "activate" | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterVersionStatus, setFilterVersionStatus] = useState<string>("");
  const [filterTaskType, setFilterTaskType] = useState<string>("");
  const [sortBy, setSortBy] = useState<"time" | "name">("time");
  const [nameSortDirection, setNameSortDirection] = useState<"asc" | "desc">("asc");
  const { isOpen: isConfirmOpen, onOpen: onConfirmOpen, onClose: onConfirmClose } = useDisclosure();
  const cancelConfirmRef = React.useRef<HTMLButtonElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const toast = useToastWithDeduplication();
  const {  user } = useAuth();

  const { checkSessionExpiry } = useSessionExpiry();
  const router = useRouter();
  
  // Check if user is GUEST or USER and redirect if so
  useEffect(() => {
    if (user?.roles?.includes('GUEST') || user?.roles?.includes('USER')) {
      toast({
        title: "Access Denied",
        description: "You do not have access to Model Management.",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      router.push('/');
    }
  }, [user, router, toast]);

  // Sync URL tab param to activeTab (e.g. when header back clears tab=2, show list)
  useEffect(() => {
    const t = router.query.tab;
    if (t === "2") setActiveTab(2);
    else if (t === "1") setActiveTab(1);
    else if (t !== "1" && t !== "2") setActiveTab(0);
  }, [router.query.tab]);

  // Fetch models on component mount
  useEffect(() => {
    const fetchModels = async () => {
      setIsLoading(true);
      try {
        const fetchedModels = await getAllModels();
        setModels(fetchedModels);
      } catch (error: any) {
        console.error("Failed to fetch models:", error);
        
        // Use centralized error handler
        const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(error);
        
          toast({
          title: showOnlyMessage ? undefined : errorTitle,
          description: errorMessage,
            status: "error",
            duration: 5000,
            isClosable: true,
          });
        // On error, set empty array
          setModels([]);
      } finally {
        setIsLoading(false);
      }
    };

    fetchModels();
  }, [toast]);

  // Fetch services: deprecate is only disabled when the model has at least one published service
  useEffect(() => {
    const fetchServices = async () => {
      try {
        const svcs = await listServicesForModels();
        const ids = new Set<string>();
        (svcs || []).forEach((s: any) => {
          const id = s.modelId ?? s.model_id;
          const published = s.isPublished === true || s.is_published === true;
          if (id && published) ids.add(String(id));
        });
        setModelIdsWithPublishedService(ids);
      } catch {
        setModelIdsWithPublishedService(new Set());
      }
    };
    fetchServices();
  }, []);

  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");
  const tableBg = useColorModeValue("white", "gray.800");
  const tableHeaderBg = useColorModeValue("gray.50", "gray.700");
  const tableRowHoverBg = useColorModeValue("gray.50", "gray.700");

  const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

  // Unique task types from models (for filter dropdown)
  const taskTypeOptions = useMemo(() => {
    const types = new Set<string>();
    models.forEach((m) => {
      if (m.task?.type) types.add(m.task.type.toUpperCase());
    });
    return Array.from(types).sort();
  }, [models]);

  // Sort key: prefer versionStatusUpdatedAt (latest update), fallback to submittedOn/updatedOn (created/updated)
  const getModelSortTime = (m: Model): number => {
    if (m.versionStatusUpdatedAt) {
      const t = new Date(m.versionStatusUpdatedAt).getTime();
      if (!Number.isNaN(t)) return t;
    }
    const submitted = m.submittedOn != null ? (m.submittedOn > 1e12 ? m.submittedOn : m.submittedOn * 1000) : 0;
    const updated = m.updatedOn != null ? (m.updatedOn > 1e12 ? m.updatedOn : m.updatedOn * 1000) : 0;
    return updated || submitted;
  };

  // Apply search (model name only) and filters (version status, task type), then sort by selected mode.
  const filteredModels = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const filtered = models.filter((m) => {
      if (q) {
        if (!(m.name ?? "").toLowerCase().includes(q)) return false;
      }
      if (filterVersionStatus) {
        const status = m.versionStatus?.toLowerCase() || "active";
        if (filterVersionStatus === "active" && status !== "active") return false;
        if (filterVersionStatus === "deprecated" && status === "active") return false;
      }
      if (filterTaskType && (m.task?.type ?? "").toUpperCase() !== filterTaskType) return false;
      return true;
    });
    // Default mode is newest-first; users can switch to explicit name sorting.
    return [...filtered].sort((a, b) => {
      const timeA = getModelSortTime(a);
      const timeB = getModelSortTime(b);
      const nameCmp = (a.name ?? "").localeCompare(b.name ?? "", undefined, { sensitivity: "base" });

      if (sortBy === "time") {
        if (timeB !== timeA) return timeB - timeA;
        return 0;
      }

      if (nameCmp !== 0) return nameSortDirection === "asc" ? nameCmp : -nameCmp;
      if (timeB !== timeA) return timeB - timeA;
      return 0;
    });
  }, [models, searchQuery, filterVersionStatus, filterTaskType, nameSortDirection, sortBy]);

  const totalModels = filteredModels.length;
  const totalPages = Math.max(1, Math.ceil(totalModels / listPageSize));
  const startRow = totalModels === 0 ? 0 : (listPage - 1) * listPageSize + 1;
  const endRow = Math.min(listPage * listPageSize, totalModels);
  const paginatedModels = filteredModels.slice((listPage - 1) * listPageSize, listPage * listPageSize);

  // Keep page in valid range when list length changes (e.g. after search/filter)
  useEffect(() => {
    if (listPage > totalPages && totalPages >= 1) setListPage(totalPages);
  }, [totalModels, listPageSize, listPage, totalPages]);

  const hasActiveFilters = filterVersionStatus !== "" || filterTaskType !== "" || searchQuery.trim() !== "";
  const clearAllFilters = () => {
    setSearchQuery("");
    setFilterVersionStatus("");
    setFilterTaskType("");
    setListPage(1);
  };

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

  const handleClearUpload = () => {
    setUploadedModelData(null);
    setParsedModelData(null);
    setValidationErrors([]);
    setUploadError(null);
    setIsUploading(false);
    setIsValidating(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleDownloadSample = () => {
    const sampleModel = {
      modelId: "example/example-model",
      version: "1.0.0",
      name: "example-model",
      description: "A sample model for demonstration purposes",
      refUrl: "https://github.com/example/example-model",
      task: {
        type: "asr"
      },
      languages: [
        {
          sourceLanguage: "hi",
          sourceScriptCode: "Deva",
          targetLanguage: "hi",
          targetScriptCode: "Deva"
        }
      ],
      license: "mit",
      domain: [
        "general"
      ],
      inferenceEndPoint: {
        schema: {
          modelProcessingType: {
            type: "batch"
          },
          request: {
            input: [
              {
                audio: "base64_encoded_audio_string"
              }
            ],
            config: {
              language: {
                sourceLanguage: "hi"
              }
            }
          },
          response: {
            output: [
              {
                transcript: "string"
              }
            ]
          }
        }
      },
      benchmarks: [
        {
          benchmarkId: "example-benchmark-001",
          name: "Example Benchmark",
          description: "Sample benchmark for evaluation",
          domain: "general",
          createdOn: "2025-01-15T10:00:00.000Z",
          languages: {
            sourceLanguage: "hi",
            targetLanguage: "hi"
          },
          score: [
            {
              metricName: "WER",
              score: "7.5"
            }
          ]
        }
      ],
      submitter: {
        name: "Example Organization",
        aboutMe: "An example organization",
        team: [
          {
            name: "John Doe",
            aboutMe: "Lead Researcher",
            oauthId: {
              oauthId: "1234567890",
              provider: "google"
            }
          }
        ]
      }
    };

    const blob = new Blob([JSON.stringify(sampleModel, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'sample-model.json';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const validateModelData = (data: any): string[] => {
    const errors: string[] = [];
    
    // Required fields
    if (!data.modelId || typeof data.modelId !== 'string' || data.modelId.trim() === '') {
      errors.push('modelId is required and must be a non-empty string');
    }
    
    if (!data.name || typeof data.name !== 'string' || data.name.trim() === '') {
      errors.push('name is required and must be a non-empty string');
    }
    
    if (!data.description || typeof data.description !== 'string' || data.description.trim() === '') {
      errors.push('description is required and must be a non-empty string');
    }
    
    if (!data.task || typeof data.task !== 'object' || !data.task.type) {
      errors.push('task is required and must be an object with a type field');
    }
    
    if (!data.languages || !Array.isArray(data.languages) || data.languages.length === 0) {
      errors.push('languages is required and must be a non-empty array');
    }
    
    if (!data.license || typeof data.license !== 'string' || data.license.trim() === '') {
      errors.push('license is required and must be a non-empty string');
    }
    
    if (!data.domain || !Array.isArray(data.domain) || data.domain.length === 0) {
      errors.push('domain is required and must be a non-empty array');
    }
    
    if (!data.inferenceEndPoint || typeof data.inferenceEndPoint !== 'object') {
      errors.push('inferenceEndPoint is required and must be an object');
    }
    
    if (!data.submitter || typeof data.submitter !== 'object' || !data.submitter.name) {
      errors.push('submitter is required and must be an object with a name field');
    }
    
    // Validate model name format (alphanumeric, hyphens, forward slashes only)
    if (data.name) {
      const namePattern = /^[a-zA-Z0-9/-]+$/;
      if (!namePattern.test(data.name)) {
        errors.push('name must contain only alphanumeric characters, hyphens (-), and forward slashes (/). Example: "example-model" or "org/model-name"');
      }
    }
    
    return errors;
  };

  const handleCreateModel = async () => {
    if (!parsedModelData) return;
    
    // Check session expiry before creating
    if (!checkSessionExpiry()) return;
    
    setIsUploading(true);
    setUploadError(null);
    
    try {
      // Prepare model data with timestamps if not present
      const currentTimestamp = Math.floor(Date.now() / 1000);
      const modelData: any = {
        ...parsedModelData,
        submittedOn: parsedModelData.submittedOn || currentTimestamp,
        updatedOn: parsedModelData.updatedOn || currentTimestamp,
        version: parsedModelData.version || "1.0",
      };

      // Create model via API
      const createdModel = await createModel(modelData);

      // Display created model data
      setUploadedModelData(createdModel);
      setParsedModelData(null);

      toast({
        title: "Model Created",
        description: "Model has been created successfully from JSON file",
        status: "success",
        duration: 3000,
        isClosable: true,
      });

      // Refresh models list
      const fetchedModels = await getAllModels();
      setModels(fetchedModels);

      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (error: any) {
      // Use centralized error handler for consistent error messages
      const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(error);
      
      setUploadError(errorMessage);
      
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMessage,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsUploading(false);
    }
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Reset previous state
    setUploadedModelData(null);
    setParsedModelData(null);
    setValidationErrors([]);
    setUploadError(null);
    setIsValidating(true);

    try {
      // Validate file type
      if (!file.name.endsWith('.json')) {
        throw new Error('Please upload a JSON file');
      }

      // Read file content
      const fileContent = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (e) => {
          resolve(e.target?.result as string);
        };
        reader.onerror = () => {
          reject(new Error('Failed to read file'));
        };
        reader.readAsText(file);
      });

      // Parse JSON
      let parsedData: any;
      try {
        parsedData = JSON.parse(fileContent);
      } catch (parseError) {
        throw new Error('Invalid JSON format. Please check your file.');
      }

      // Validate that it's an object
      if (typeof parsedData !== 'object' || parsedData === null || Array.isArray(parsedData)) {
        throw new Error('JSON must be an object');
      }

      // Validate required fields
      const errors = validateModelData(parsedData);
      if (errors.length > 0) {
        setValidationErrors(errors);
        setUploadError(errors.join('; '));
        setIsValidating(false);
        return;
      }

      // Store parsed data for review and creation
      setParsedModelData(parsedData);
      setValidationErrors([]);
      setUploadError(null);

      toast({
        title: "File Validated",
        description: "JSON file has been validated successfully. Review the data below and click 'Register Model' to proceed.",
        status: "success",
        duration: 3000,
        isClosable: true,
      });
    } catch (error: any) {
      // Use centralized error handler for consistent error messages
      const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(error);
      
      setUploadError(errorMessage);
      setValidationErrors([]);
      
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMessage,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsValidating(false);
    }
  };

  const handleViewModel = async (modelId: string) => {
    // Check session expiry before viewing model
    if (!checkSessionExpiry()) return;
    
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
      router.replace({ pathname: "/model-management", query: { ...router.query, tab: "2" } }, undefined, { shallow: true });
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
    
    // Check session expiry before updating
    if (!checkSessionExpiry()) return;

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

  const handleDeprecateModel = async (model: Model) => {
    // Check session expiry before deprecating
    if (!checkSessionExpiry()) return;
    
    if (!model.modelId || !model.version) {
      toast({
        title: "Deprecate Failed",
        description: "Model ID and version are required",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      return;
    }

    setUpdatingModelId(model.modelId);

    try {
      await updateModel({
        modelId: model.modelId,
        version: model.version,
        versionStatus: "DEPRECATED",
      });

      toast({
        title: "Model deprecated",
        description: `${model.name || model.modelId} has been deprecated successfully.`,
        status: "success",
        duration: 5000,
        isClosable: true,
      });
      
      // Refresh models list and selected model
      const fetchedModels = await getAllModels();
      setModels(fetchedModels);
      if (selectedModel && selectedModel.modelId === model.modelId) {
        const updatedModel = await getModelById(model.modelId);
        setSelectedModel(updatedModel);
        setUpdateFormData(updatedModel);
      }
    } catch (error: any) {
      const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(error);
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMessage,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setUpdatingModelId(null);
    }
  };

  const handleActivateModel = async (model: Model) => {
    // Check session expiry before activating
    if (!checkSessionExpiry()) return;
    
    if (!model.modelId || !model.version) {
      toast({
        title: "Activate Failed",
        description: "Model ID and version are required",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      return;
    }

    setUpdatingModelId(model.modelId);

    try {
      await updateModel({
        modelId: model.modelId,
        version: model.version,
        versionStatus: "ACTIVE",
      });

      toast({
        title: "Model activated",
        description: `${model.name || model.modelId} has been activated successfully.`,
        status: "success",
        duration: 5000,
        isClosable: true,
      });

      // Refresh models list and selected model
      const fetchedModels = await getAllModels();
      setModels(fetchedModels);
      if (selectedModel && selectedModel.modelId === model.modelId) {
        const updatedModel = await getModelById(model.modelId);
        setSelectedModel(updatedModel);
        setUpdateFormData(updatedModel);
      }
    } catch (error: any) {
      const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(error);
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMessage,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setUpdatingModelId(null);
    }
  };

  const openConfirmDialog = (action: "deprecate" | "activate", model: Model) => {
    setModelToConfirm(model);
    setConfirmAction(action);
    onConfirmOpen();
  };

  const handleConfirmAction = async () => {
    if (!modelToConfirm || !confirmAction) return;
    onConfirmClose();
    if (confirmAction === "deprecate") {
      await handleDeprecateModel(modelToConfirm);
    } else {
      await handleActivateModel(modelToConfirm);
    }
    setModelToConfirm(null);
    setConfirmAction(null);
  };

  const closeConfirmDialog = () => {
    onConfirmClose();
    setModelToConfirm(null);
    setConfirmAction(null);
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
                    <Heading size="lg" color="gray.800" mb={1} userSelect="none" cursor="default" tabIndex={-1}>
                     Model Management
                    </Heading>
                    <Text color="gray.600" fontSize="sm" userSelect="none" cursor="default">
                    Manage and configure AI models
                    </Text>
                  </Box>
        
                  <Grid
                    gap={8}
                    w="full"
                    mx="auto"
                  >
                    <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px">
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
                const q = { ...router.query } as Record<string, string>;
                if (index === 0) delete q.tab;
                else q.tab = String(index);
                router.replace({ pathname: "/model-management", query: q }, undefined, { shallow: true });
              }}
            >
              <TabList>
                <Tab fontWeight="semibold">Model Registry</Tab>
                <Tab fontWeight="semibold">Register Model</Tab>
                {isViewingModel && selectedModel && (
                  <Tab fontWeight="semibold">View Model</Tab>
                )}
              </TabList>

              <TabPanels>
                {/* Model Registry Tab */}
                <TabPanel px={0} pt={6}>
                  <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
                    <CardHeader>
                      <Heading size="md" color="gray.700" userSelect="none" cursor="default">
                        Model Registry
                      </Heading>
                    </CardHeader>
                    <CardBody>
                      {isLoading ? (
                        <Box textAlign="center" py={8}>
                          <Text color="gray.500">Loading models...</Text>
                        </Box>
                      ) : (
                        <>
                        {/* Search and filters - consistent with portal patterns */}
                        <VStack align="stretch" spacing={4} mb={4}>
                          <TableFilterToolbar
                            hasActiveFilters={hasActiveFilters}
                            onClear={clearAllFilters}
                            align="flex-end"
                          >
                            <FormControl w={{ base: "full", md: "280px" }}>
                              <FormLabel fontSize="sm" fontWeight="medium" mb={1}>
                                Search
                              </FormLabel>
                              <InputGroup>
                                <InputLeftElement pointerEvents="none">
                                  <SearchIcon color="gray.400" />
                                </InputLeftElement>
                                <Input
                                  placeholder="Search by model name..."
                                  value={searchQuery}
                                  onChange={(e) => setSearchQuery(e.target.value)}
                                  bg={cardBg}
                                  pl={10}
                                  size="sm"
                                />
                              </InputGroup>
                            </FormControl>
                            <FormControl w={{ base: "full", sm: "140px" }}>
                              <FormLabel fontSize="sm" fontWeight="medium" mb={1}>
                                Status
                              </FormLabel>
                              <Select
                                size="sm"
                                value={filterVersionStatus}
                                onChange={(e) => {
                                  setFilterVersionStatus(e.target.value);
                                  setListPage(1);
                                }}
                                bg={cardBg}
                              >
                                <option value="">All</option>
                                <option value="active">Active</option>
                                <option value="deprecated">Deprecated</option>
                              </Select>
                            </FormControl>
                            <FormControl w={{ base: "full", sm: "160px" }}>
                              <FormLabel fontSize="sm" fontWeight="medium" mb={1}>
                                Task type
                              </FormLabel>
                              <Select
                                size="sm"
                                value={filterTaskType}
                                onChange={(e) => {
                                  setFilterTaskType(e.target.value);
                                  setListPage(1);
                                }}
                                bg={cardBg}
                              >
                                <option value="">All</option>
                                {taskTypeOptions.map((t) => (
                                  <option key={t} value={t}>{t}</option>
                                ))}
                              </Select>
                            </FormControl>
                          </TableFilterToolbar>
                          {hasActiveFilters && (
                            <HStack spacing={2} flexWrap="wrap">
                              {searchQuery.trim() && (
                                <Badge
                                  colorScheme="blue"
                                  fontSize="xs"
                                  px={2}
                                  py={1}
                                  cursor="pointer"
                                  onClick={() => { setSearchQuery(""); setListPage(1); }}
                                  _hover={{ opacity: 0.8 }}
                                >
                                  Search: &quot;{searchQuery.trim()}&quot; ×
                                </Badge>
                              )}
                              {filterVersionStatus && (
                                <Badge
                                  colorScheme="gray"
                                  fontSize="xs"
                                  px={2}
                                  py={1}
                                  cursor="pointer"
                                  onClick={() => { setFilterVersionStatus(""); setListPage(1); }}
                                  _hover={{ opacity: 0.8 }}
                                >
                                  Status: {filterVersionStatus === "active" ? "Active" : "Deprecated"} ×
                                </Badge>
                              )}
                              {filterTaskType && (
                                <Badge
                                  colorScheme="gray"
                                  fontSize="xs"
                                  px={2}
                                  py={1}
                                  cursor="pointer"
                                  onClick={() => { setFilterTaskType(""); setListPage(1); }}
                                  _hover={{ opacity: 0.8 }}
                                >
                                  Task: {filterTaskType} ×
                                </Badge>
                              )}
                            </HStack>
                          )}
                        </VStack>

                        {filteredModels.length === 0 ? (
                          <Box textAlign="center" py={8}>
                            <Text color="gray.500">
                              No results found.
                              {models.length === 0
                                ? " No models in the registry yet."
                                : " Try adjusting your search or filters."}
                            </Text>
                          </Box>
                        ) : (
                        <Box maxH="60vh" overflowY="auto" overflowX="hidden">
                          <Table variant="simple" bg={tableBg} size="sm" w="100%">
                            <Thead bg={tableHeaderBg}>
                              <Tr>
                                <Th>
                                  <TableSortHeader
                                    label="Name"
                                    direction={nameSortDirection}
                                    onAsc={() => {
                                      setSortBy("name");
                                      setNameSortDirection("asc");
                                      setListPage(1);
                                    }}
                                    onDesc={() => {
                                      setSortBy("name");
                                      setNameSortDirection("desc");
                                      setListPage(1);
                                    }}
                                    ascAriaLabel="Sort models by name ascending"
                                    descAriaLabel="Sort models by name descending"
                                  />
                                </Th>
                                <Th>Version</Th>
                                <Th> Status</Th>
                                <Th>Task Type</Th>
                                <Th>Actions</Th>
                              </Tr>
                            </Thead>
                            <Tbody>
                              {paginatedModels.map((model) => (
                              <Tr 
                                key={model.modelId} 
                                _hover={{ bg: tableRowHoverBg, cursor: "pointer" }}
                                onClick={() => handleViewModel(model.modelId)}
                              >
                                <Td>
                                  <Text fontSize="sm" noOfLines={1} title={model.name}>
                                    {model.name}
                                  </Text>
                                </Td>
                                <Td>
                                  <Text fontSize="sm" fontWeight="medium">
                                    {model.version || "1.0"}
                                  </Text>
                                </Td>
                                <Td>
                                  <Badge
                                    colorScheme={model.versionStatus?.toLowerCase() === "active" || !model.versionStatus ? "green" : "gray"}
                                    fontSize="xs"
                                  >
                                    {model.versionStatus?.toLowerCase() === "active" || !model.versionStatus ? "ACTIVE" : "DEPRECATED"}
                                  </Badge>
                                </Td>
                                <Td>
                                  <Badge
                                    colorScheme={getTaskColor(model.task.type)}
                                    fontSize="xs"
                                  >
                                    {model.task.type.toUpperCase()}
                                  </Badge>
                                </Td>
                                <Td onClick={(e) => e.stopPropagation()}>
                                  <HStack spacing={3} align="center">
                                    <Tooltip label="View" placement="top" hasArrow>
                                      <IconButton
                                        aria-label="View"
                                        icon={<ViewIcon />}
                                        size="sm"
                                        variant="ghost"
                                        colorScheme="blue"
                                        _hover={{ bg: "blue.50" }}
                                        onClick={() => handleViewModel(model.modelId)}
                                      />
                                    </Tooltip>
                                    {(model.versionStatus?.toLowerCase() === "active" || !model.versionStatus) && !modelIdsWithPublishedService.has(model.modelId) ? (
                                      <Tooltip label="Deprecate model" placement="top" hasArrow>
                                        <Box as="span" display="inline-flex" alignItems="center">
                                          <Switch
                                            size="md"
                                            colorScheme="green"
                                            isChecked={true}
                                            onChange={() => openConfirmDialog("deprecate", model)}
                                            isDisabled={updatingModelId !== null}
                                            onClick={(e) => e.stopPropagation()}
                                          />
                                        </Box>
                                      </Tooltip>
                                    ) : (model.versionStatus?.toLowerCase() !== "active" && model.versionStatus) ? (
                                      <Tooltip label="Activate model" placement="top" hasArrow>
                                        <Box as="span" display="inline-flex" alignItems="center">
                                          <Switch
                                            size="md"
                                            colorScheme="green"
                                            isChecked={false}
                                            onChange={() => openConfirmDialog("activate", model)}
                                            isDisabled={updatingModelId !== null}
                                            onClick={(e) => e.stopPropagation()}
                                          />
                                        </Box>
                                      </Tooltip>
                                    ) : null}
                                  </HStack>
                                </Td>
                              </Tr>
                              ))}
                            </Tbody>
                          </Table>
                        </Box>
                        )}
                      {!isLoading && filteredModels.length > 0 && (
                        <TablePaginationBar
                          startRow={startRow}
                          endRow={endRow}
                          totalItems={totalModels}
                          page={listPage}
                          totalPages={totalPages}
                          pageSize={listPageSize}
                          pageSizeOptions={PAGE_SIZE_OPTIONS}
                          onPageSizeChange={(value) => {
                            setListPageSize(value);
                            setListPage(1);
                          }}
                          onFirst={() => setListPage(1)}
                          onPrev={() => setListPage((p) => Math.max(1, p - 1))}
                          onNext={() => setListPage((p) => Math.min(totalPages, p + 1))}
                          onLast={() => setListPage(totalPages)}
                          canPrev={listPage > 1}
                          canNext={listPage < totalPages}
                          borderColor={cardBorder}
                          bg={cardBg}
                        />
                      )}
                        </>
                      )}
                    </CardBody>
                  </Card>
                </TabPanel>

                {/* Create Model Tab */}
                <TabPanel px={0} pt={6}>
                  <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
                    <CardHeader>
                      <Heading size="md" color="gray.700" userSelect="none" cursor="default">
                        Register New Model
                      </Heading>
                    </CardHeader>
                    <CardBody>
                        <VStack spacing={6} align="stretch">
                        {/* File Upload Section */}
                        <Box>
                          <FormControl>
                            <HStack justify="space-between" mb={2}>
                              <FormLabel fontWeight="semibold" mb={0}>Upload JSON File</FormLabel>
                              <Button
                                size="sm"
                                colorScheme="blue"
                                variant="outline"
                                onClick={handleDownloadSample}
                              >
                                📥 Download Sample JSON
                              </Button>
                            </HStack>
                              <Input
                              ref={fileInputRef}
                              type="file"
                              accept=".json"
                              onChange={handleFileUpload}
                              disabled={isUploading || isValidating}
                                bg="white"
                              p={2}
                            />
                            <Text fontSize="sm" color="gray.500" mt={2}>
                              Upload a JSON file containing the model data. The file will be validated before you can create the model.
                            </Text>
                            <Box mt={2} p={3} bg="blue.50" borderRadius="md" border="1px solid" borderColor="blue.200">
                              <Text fontSize="xs" fontWeight="semibold" color="blue.700" mb={1}>
                                Required Fields:
                              </Text>
                              <Text fontSize="xs" color="blue.600">
                                modelId, name, description, task (with type), languages, license, domain, inferenceEndPoint, submitter. Optional: version (defaults to &quot;1.0&quot;), refUrl, benchmarks. Timestamps (submittedOn, updatedOn) will be auto-added if not present.
                              </Text>
                            </Box>
                            </FormControl>
                        </Box>

                        {/* Validating State */}
                        {isValidating && (
                          <Center py={8}>
                            <VStack spacing={4}>
                              <Spinner size="lg" color="blue.500" />
                              <Text color="gray.600">Validating JSON file...</Text>
                            </VStack>
                          </Center>
                        )}

                        {/* Loading State */}
                        {isUploading && (
                          <Center py={8}>
                            <VStack spacing={4}>
                              <Spinner size="lg" color="blue.500" />
                              <Text color="gray.600">Creating model...</Text>
                            </VStack>
                          </Center>
                        )}

                        {/* Validation Errors Display */}
                        {validationErrors.length > 0 && (
                          <Alert status="error" borderRadius="md">
                            <AlertIcon />
                            <AlertDescription>
                              <VStack align="stretch" spacing={3}>
                                <Box>
                                  <Text fontWeight="semibold" mb={2}>Validation Failed</Text>
                                  <Text mb={2}>Please fix the following errors:</Text>
                                  <Box as="ul" pl={4}>
                                    {validationErrors.map((error, index) => (
                                      <Text key={index} as="li" fontSize="sm" mb={1}>
                                        {error}
                                      </Text>
                                    ))}
                                  </Box>
                                </Box>
                                <Button
                                  size="sm"
                                  colorScheme="gray"
                                  variant="outline"
                                  onClick={handleClearUpload}
                                  alignSelf="flex-start"
                                >
                                  Clear & Upload New File
                                </Button>
                              </VStack>
                            </AlertDescription>
                          </Alert>
                        )}

                        {/* General Error Display */}
                        {uploadError && validationErrors.length === 0 && (
                          <Alert status="error" borderRadius="md">
                            <AlertIcon />
                            <AlertDescription>
                              <VStack align="stretch" spacing={3}>
                                <Box>
                                  <Text fontWeight="semibold" mb={2}>Error</Text>
                                  <Text>{uploadError}</Text>
                                </Box>
                                <Button
                                  size="sm"
                                  colorScheme="gray"
                                  variant="outline"
                                  onClick={handleClearUpload}
                                  alignSelf="flex-start"
                                >
                                  Clear & Upload New File
                                </Button>
                              </VStack>
                            </AlertDescription>
                          </Alert>
                        )}

                        {/* Parsed Data - Ready for Creation */}
                        {parsedModelData && !isUploading && !isValidating && (
                          <Box>
                            <Alert status="success" borderRadius="md" mb={4}>
                              <AlertIcon />
                              <AlertDescription>
                                JSON file validated successfully! Review the data below and click &quot;Register Model&quot; to proceed.
                              </AlertDescription>
                            </Alert>
                            <Box>
                              <Heading size="sm" color="gray.700" mb={4} userSelect="none" cursor="default">
                                Parsed Model Data
                              </Heading>
                              <Box
                                bg="gray.50"
                                p={4}
                                borderRadius="md"
                                border="1px solid"
                                borderColor="gray.200"
                                maxH="600px"
                                overflowY="auto"
                              >
                                <Code
                                  display="block"
                                  whiteSpace="pre-wrap"
                                  fontSize="sm"
                                  p={4}
                                  bg="white"
                                  borderRadius="md"
                                >
                                  {JSON.stringify(parsedModelData, null, 2)}
                                </Code>
                              </Box>
                              <HStack spacing={3} mt={4}>
                                <Button
                                  colorScheme="green"
                                  onClick={handleCreateModel}
                                  isLoading={isUploading}
                                  loadingText="Creating..."
                                >
                                  Register Model
                                </Button>
                                <Button
                                  colorScheme="gray"
                                  variant="outline"
                                  onClick={handleClearUpload}
                                >
                                  Cancel
                                </Button>
                              </HStack>
                            </Box>
                          </Box>
                        )}

                        {/* Success - Model Created */}
                        {uploadedModelData && !isUploading && (
                          <Box>
                            <Alert status="success" borderRadius="md" mb={4}>
                              <AlertIcon />
                              <AlertDescription>
                                Model created successfully! Model data is displayed below.
                              </AlertDescription>
                            </Alert>
                            <Box>
                              <Heading size="sm" color="gray.700" mb={4} userSelect="none" cursor="default">
                                Created Model Data
                              </Heading>
                              <Box
                                bg="gray.50"
                                p={4}
                                borderRadius="md"
                                border="1px solid"
                                borderColor="gray.200"
                                maxH="600px"
                                overflowY="auto"
                              >
                                <Code
                                  display="block"
                                  whiteSpace="pre-wrap"
                                  fontSize="sm"
                                  p={4}
                                  bg="white"
                                  borderRadius="md"
                                >
                                  {JSON.stringify(uploadedModelData, null, 2)}
                                </Code>
                              </Box>
                            <Button
                                mt={4}
                                colorScheme="blue"
                              onClick={handleClearUpload}
                              >
                                Upload Another Model
                            </Button>
                            </Box>
                          </Box>
                        )}
                        </VStack>
                    </CardBody>
                  </Card>
                </TabPanel>

                {/* View Model Tab */}
                {isViewingModel && selectedModel && (
                  <TabPanel px={0} pt={6}>
                    <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
                      <CardHeader>
                        <HStack justify="space-between" align="center">
                          <Heading size="md" color="gray.700" userSelect="none" cursor="default">
                           {selectedModel.name}
                          </Heading>
                          <HStack spacing={2}>
                            {(selectedModel.versionStatus?.toLowerCase() === "active" || !selectedModel.versionStatus) && (
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
                            {(selectedModel.versionStatus?.toLowerCase() === "active" || !selectedModel.versionStatus) && !modelIdsWithPublishedService.has(selectedModel.modelId) ? (
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
                            ) : (selectedModel.versionStatus?.toLowerCase() !== "active" && selectedModel.versionStatus) ? (
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
                            <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                              <Box>
                                <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                                  Model ID
                                </Text>
                                <Text fontSize="md" wordBreak="break-all">{selectedModel.modelId}</Text>
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
                                  colorScheme={selectedModel.versionStatus?.toLowerCase() === "active" || !selectedModel.versionStatus ? "green" : "gray"}
                                  fontSize="sm"
                                  p={2}
                                >
                                  {selectedModel.versionStatus?.toLowerCase() === "active" || !selectedModel.versionStatus ? "ACTIVE" : "DEPRECATED"}
                                </Badge>
                              </Box>
                              <Box>
                                <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                                  Task type
                                </Text>
                                <Badge
                                  colorScheme={getTaskColor(selectedModel.task.type)}
                                  fontSize="sm"
                                  p={2}
                                >
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
                                  <Text color="gray.500" fontSize="sm">No domains specified</Text>
                                )}
                              </HStack>
                            </Box>
                          </VStack>
                        )}
                        {/* Editing disabled for models after creation - edit form removed */}
                      </CardBody>
                    </Card>
                  </TabPanel>
                )}
              </TabPanels>
            </Tabs>
          </Card></Grid>
     </VStack>
      </ContentLayout>

      <ConfirmDialog
        isOpen={isConfirmOpen}
        onClose={closeConfirmDialog}
        onConfirm={handleConfirmAction}
        title={confirmAction === "deprecate" ? "Deprecate model" : "Activate model"}
        body={
          confirmAction === "deprecate" ? (
            <>
              Are you sure you want to deprecate{" "}
              <strong>{modelToConfirm?.name || modelToConfirm?.modelId}</strong>?
              Deprecated models cannot be used for new services.
            </>
          ) : (
            <>
              Are you sure you want to activate{" "}
              <strong>{modelToConfirm?.name || modelToConfirm?.modelId}</strong>?
              The model will be available for services again.
            </>
          )
        }
        confirmLabel="Confirm"
        cancelLabel="Cancel"
        confirmColorScheme={confirmAction === "deprecate" ? "orange" : "green"}
        isConfirmLoading={updatingModelId === modelToConfirm?.modelId}
        confirmLoadingText={confirmAction === "deprecate" ? "Deprecating..." : "Activating..."}
        leastDestructiveRef={cancelConfirmRef}
      />
    </>
  );
};

export default ModelManagementPage;

