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
  Select,
  Switch,
  Badge,
  Text,
  VStack,
  HStack,
  useDisclosure,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
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
import { ViewIcon } from "@chakra-ui/icons";
import { useRouter } from "next/router";
import React, { useState, useEffect, useRef, useMemo, useCallback } from "react";
import ContentLayout from "../components/common/ContentLayout";
import ManagementPageHeader from "../components/common/ManagementPageHeader";
import {
  fetchAllModelsMatchingFilters,
  createModel,
  getModelById,
  updateModel,
} from "../services/modelManagementService";
import type { ModelCreateRequest, ModelDetails, ModelUpdateRequest, TaskSpec } from "../types/platform";
import { listServices as listServicesForModels } from "../services/servicesManagementService";
import { useAuth } from "../hooks/useAuth";
import { isRegistryReadOnlyUser } from "../utils/rbac";
import { useSessionExpiry } from "../hooks/useSessionExpiry";
import { parseError, showError } from "../utils/errorHandler";
import { showToast } from "../utils/toast";
import ConfirmDialog from "../components/common/ConfirmDialog";
import { useAdminTableSurface } from "../components/common/TableControls";
import AdminDataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  TableSearchField,
  TableSelectField,
  type AdminTableColumn,
} from "../components/common/AdminDataTable";
import {
  MODEL_VERSION,
  MODEL_VERSION_FILTER_LIST,
  MODEL_FIELD_LIMITS,
  MODEL_API_KEY_REDACTED,
  formatModelTaskTypeLabel,
  formatModelVersionFilterLabel,
  formatModelVersionStatusLabel,
  isModelVersionStatusActive,
} from "../config/constants";
import { useInferenceTypes } from "../hooks/useInferenceTypes";

/** Registry UI model row — requires fields used in forms/tables. */
type Model = ModelDetails & {
  name: string;
  description: string;
  languages: NonNullable<ModelDetails["languages"]>;
  domain: string[];
  license: string;
  adapterConfig?: Record<string, unknown> | null;
  schema?: Record<string, unknown> | null;
  source: string;
  task: NonNullable<ModelDetails["task"]>;
};

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
  const { taskTypeNames, isLoading: isLoadingTaskTypes } = useInferenceTypes();
  const enabledTaskTypesParam =
    taskTypeNames.length > 0 ? taskTypeNames.join(",") : undefined;
  const didInitTaskTypeFilter = useRef(false);
  const [taskTypeFilterReady, setTaskTypeFilterReady] = useState(false);
  useEffect(() => {
    if (didInitTaskTypeFilter.current || isLoadingTaskTypes) return;
    didInitTaskTypeFilter.current = true;
    if (taskTypeNames.length > 0) setFilterTaskType(taskTypeNames[0]);
    setTaskTypeFilterReady(true);
  }, [isLoadingTaskTypes, taskTypeNames]);
  const [sortBy, setSortBy] = useState<"time" | "name">("time");
  const [nameSortDirection, setNameSortDirection] = useState<"asc" | "desc">("asc");
  const { isOpen: isConfirmOpen, onOpen: onConfirmOpen, onClose: onConfirmClose } = useDisclosure();
  const cancelConfirmRef = React.useRef<HTMLButtonElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { user } = useAuth();
  const isRegistryReadOnly = isRegistryReadOnlyUser(user?.roles);
  /** View tab index shifts when the create/register tab is hidden (tenant admin read-only). */
  const viewTabIndex = isRegistryReadOnly ? 1 : 2;

  const { checkSessionExpiry } = useSessionExpiry();
  const router = useRouter();

  // Check if user is GUEST or USER and redirect if so
  useEffect(() => {
    if (user?.roles?.includes('GUEST') || user?.roles?.includes('USER')) {
      showToast({
        type: "error",
        message: "You do not have access to Model Management.",
      });
      router.push('/');
    }
  }, [user, router]);

  // Sync URL tab param to activeTab (e.g. when header back clears tab=2, show list)
  useEffect(() => {
    const t = router.query.tab;
    if (isRegistryReadOnly && (t === "1" || t === "create")) {
      setActiveTab(0);
      if (router.query.tab) {
        const q = { ...router.query } as Record<string, string>;
        delete q.tab;
        router.replace({ pathname: "/model-management", query: q }, undefined, { shallow: true });
      }
      return;
    }
    if (t === "2") setActiveTab(viewTabIndex);
    else if (t === "1") setActiveTab(1);
    else if (t !== "1" && t !== "2") setActiveTab(0);
  }, [router.query.tab, isRegistryReadOnly, router, viewTabIndex]);

  // Fetch all models for current task/status filters (paginated API walk) for client search + pagination
  const fetchModels = useCallback(async () => {
    setIsLoading(true);
    try {
      const result = await fetchAllModelsMatchingFilters({
        taskType: filterTaskType || undefined,
        taskTypes: enabledTaskTypesParam,
        versionStatus: filterVersionStatus || undefined,
      });
      setModels(result.items as unknown as Model[]);
    } catch (error: any) {
      console.error("Failed to fetch models:", error);
      showError(error);
      setModels([]);
    } finally {
      setIsLoading(false);
    }
  }, [filterTaskType, filterVersionStatus, enabledTaskTypesParam]);

  useEffect(() => {
    if (!taskTypeFilterReady) return;
    fetchModels();
  }, [fetchModels, taskTypeFilterReady]);

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

  const { cardBg, borderColor: cardBorder } = useAdminTableSurface();

  // Client-side name filter + sort over the full fetched registry list.
  const registryTableItems = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const filtered = q
      ? models.filter((m) => (m.name ?? "").toLowerCase().includes(q))
      : models;
    if (sortBy === "time") return filtered;
    return [...filtered].sort((a, b) => {
      const nameCmp = (a.name ?? "").localeCompare(b.name ?? "", undefined, { sensitivity: "base" });
      if (nameCmp !== 0) return nameSortDirection === "asc" ? nameCmp : -nameCmp;
      return 0;
    });
  }, [models, searchQuery, sortBy, nameSortDirection]);

  const hasActiveFilters = filterVersionStatus !== "" || searchQuery.trim() !== "";
  const clearAllFilters = () => {
    setSearchQuery("");
    setFilterVersionStatus("");
    if (taskTypeNames.length > 0) setFilterTaskType(taskTypeNames[0]);
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
    value: string | TaskSpec | string[]
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
      version: "v1",
      name: "test-llm-2",
      description:
        "A sample LLM model for demonstration purposes. Description must be at least 25 characters.",
      refUrl: "https://github.com/example/example-model",
      task: {
        type: "llm",
      },
      languages: [
        {
          sourceLanguage: "hi",
          sourceLanguageName: "Hindi",
          sourceScriptCode: "Deva",
          targetLanguage: "hi",
          targetLanguageName: "Hindi",
          targetScriptCode: "Deva",
        },
      ],
      isLangDetectionEnabled: false,
      isMultilingual: false,
      license: "mit",
      licenseUrl: "https://opensource.org/licenses/MIT",
      domain: ["general"],
      adapterConfig: {
        model_name: "google/gemma-4-31B-it",
      },
      schema: {
        request: {
          model: "google/gemma-5-E4B-it",
          messages: [
            {
              role: "user",
              content: "Hello",
            },
          ],
        },
        response: {},
        model_name: null,
        modelProcessingType: null,
      },
      trainingDataset: {
        description:
          "Sample training dataset description for the example LLM model registration.",
        datasetId: "example-LLM-corpus-v1",
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
            targetLanguage: "hi",
          },
          score: [
            {
              metricName: "WER",
              score: "7.5",
            },
          ],
        },
      ],
      submitter: {
        name: "Example Org",
        aboutMe: "An example organization",
        team: [
          {
            name: "John Doe",
            aboutMe: "Lead Researcher",
            oauthId: {
              oauthId: "1234567890",
              provider: "google",
            },
          },
        ],
      },
    };

    const blob = new Blob([JSON.stringify(sampleModel, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "sample-model.json";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const validateModelData = (data: any): string[] => {
    const errors: string[] = [];
    const {
      NAME_MIN,
      NAME_MAX,
      VERSION_MIN,
      VERSION_MAX,
      DESCRIPTION_MIN,
      DESCRIPTION_MAX,
      REF_URL_MIN,
      REF_URL_MAX,
      LICENSE_URL_MAX,
      SUBMITTER_NAME_MIN,
      SUBMITTER_NAME_MAX,
      TEAM_NAME_MIN,
      TEAM_NAME_MAX,
    } = MODEL_FIELD_LIMITS;

    // Enum membership (license/domain/language/script) is enforced by the API —
    // do not duplicate ULCA closed lists here. Validate shape + lengths only.

    if (!data.name || typeof data.name !== "string" || data.name.trim() === "") {
      errors.push("name is required and must be a non-empty string");
    } else {
      const name = data.name.trim();
      if (name.length < NAME_MIN || name.length > NAME_MAX) {
        errors.push(`name must be ${NAME_MIN}–${NAME_MAX} characters (got ${name.length})`);
      }
      if (/\s/.test(name)) {
        errors.push("name must not contain spaces");
      }
      const namePattern = /^[a-zA-Z0-9/-]+$/;
      if (!namePattern.test(name)) {
        errors.push(
          'name must contain only alphanumeric characters, hyphens (-), and forward slashes (/). Example: "example-model" or "org/model-name"'
        );
      }
    }

    if (!data.version || typeof data.version !== "string" || data.version.trim() === "") {
      errors.push("version is required and must be a non-empty string");
    } else if (
      data.version.trim().length < VERSION_MIN ||
      data.version.trim().length > VERSION_MAX
    ) {
      errors.push(`version must be ${VERSION_MIN}–${VERSION_MAX} characters`);
    }

    if (!data.description || typeof data.description !== "string" || data.description.trim() === "") {
      errors.push("description is required and must be a non-empty string");
    } else {
      const descLen = data.description.length;
      if (descLen < DESCRIPTION_MIN || descLen > DESCRIPTION_MAX) {
        errors.push(
          `description must be ${DESCRIPTION_MIN}–${DESCRIPTION_MAX} characters (got ${descLen})`
        );
      }
    }

    if (data.refUrl != null && data.refUrl !== "") {
      if (typeof data.refUrl !== "string") {
        errors.push("refUrl must be a string when provided");
      } else if (data.refUrl.length < REF_URL_MIN || data.refUrl.length > REF_URL_MAX) {
        errors.push(`refUrl must be ${REF_URL_MIN}–${REF_URL_MAX} characters when provided`);
      }
    }

    if (!data.task || typeof data.task !== "object" || !data.task.type) {
      errors.push("task is required and must be an object with a type field");
    }

    if (data.languages != null && !Array.isArray(data.languages)) {
      errors.push("languages must be an array when provided");
    } else if (Array.isArray(data.languages)) {
      data.languages.forEach((pair: any, index: number) => {
        if (!pair || typeof pair !== "object") {
          errors.push(`languages[${index}] must be an object`);
        } else if (!pair.sourceLanguage || typeof pair.sourceLanguage !== "string") {
          errors.push(`languages[${index}].sourceLanguage is required`);
        }
      });
    }

    if (!data.license || typeof data.license !== "string" || data.license.trim() === "") {
      errors.push("license is required and must be a non-empty string");
    }

    if (data.licenseUrl != null && data.licenseUrl !== "") {
      if (typeof data.licenseUrl !== "string") {
        errors.push("licenseUrl must be a string when provided");
      } else if (data.licenseUrl.length > LICENSE_URL_MAX) {
        errors.push(`licenseUrl must be at most ${LICENSE_URL_MAX} characters`);
      }
    }

    if (!data.domain || !Array.isArray(data.domain) || data.domain.length === 0) {
      errors.push("domain is required and must be a non-empty array");
    }

    if (!data.trainingDataset || typeof data.trainingDataset !== "object") {
      errors.push(
        "trainingDataset is required and must be an object with a description field"
      );
    } else if (
      !data.trainingDataset.description ||
      typeof data.trainingDataset.description !== "string" ||
      data.trainingDataset.description.trim() === ""
    ) {
      errors.push("trainingDataset.description is required and must be a non-empty string");
    }

    if (data.adapterConfig != null && typeof data.adapterConfig !== "object") {
      errors.push("adapterConfig must be an object when provided");
    }

    if (data.schema != null && (typeof data.schema !== "object" || Array.isArray(data.schema))) {
      errors.push("schema must be an object when provided");
    }

    if (!data.submitter || typeof data.submitter !== "object" || !data.submitter.name) {
      errors.push("submitter is required and must be an object with a name field");
    } else {
      const submitterName = String(data.submitter.name);
      if (
        submitterName.length < SUBMITTER_NAME_MIN ||
        submitterName.length > SUBMITTER_NAME_MAX
      ) {
        errors.push(
          `submitter.name must be ${SUBMITTER_NAME_MIN}–${SUBMITTER_NAME_MAX} characters`
        );
      }
      if (Array.isArray(data.submitter.team)) {
        data.submitter.team.forEach((member: any, index: number) => {
          if (!member?.name || typeof member.name !== "string") {
            errors.push(`submitter.team[${index}].name is required`);
          } else if (
            member.name.length < TEAM_NAME_MIN ||
            member.name.length > TEAM_NAME_MAX
          ) {
            errors.push(
              `submitter.team[${index}].name must be ${TEAM_NAME_MIN}–${TEAM_NAME_MAX} characters`
            );
          }
        });
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
      const { modelId: _ignoredModelId, ...rest } = parsedModelData;
      const modelData: ModelCreateRequest = {
        ...rest,
        license:
          typeof rest.license === "string"
            ? (rest.license.toLowerCase() as ModelCreateRequest["license"])
            : rest.license,
        submittedOn: parsedModelData.submittedOn || currentTimestamp,
        updatedOn: parsedModelData.updatedOn || currentTimestamp,
      };

      // Create model via API
      const createdModel = await createModel(modelData);

      // Display created model data
      setUploadedModelData(createdModel);
      setParsedModelData(null);

      showToast({
        type: "success",
        message: "Model has been created successfully from JSON file",
      });

      // Refresh models list
      await fetchModels();

      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (error: any) {
      // Use centralized error handler for consistent error messages
      const { message: errorMessage } = parseError(error);
      setUploadError(errorMessage);
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

      showToast({
        type: "success",
        message: "JSON file has been validated successfully. Review the data below and click 'Register Model' to proceed.",
      });
    } catch (error: any) {
      // Use centralized error handler for consistent error messages
      const { message: errorMessage } = parseError(error);
      setUploadError(errorMessage);
      setValidationErrors([]);
    } finally {
      setIsValidating(false);
    }
  };

  const handleViewModel = async (modelId: string) => {
    // Check session expiry before viewing model
    if (!checkSessionExpiry()) return;

    try {
      const model = await getModelById(modelId);
      setSelectedModel(model as unknown as Model);
      setUpdateFormData({
        ...(model as unknown as Partial<Model>),
        task: { type: model.task?.type ?? model.task_type ?? model.taskType ?? "" },
      });
      setIsViewingModel(true);
      setActiveTab(viewTabIndex);
      router.replace({ pathname: "/model-management", query: { ...router.query, tab: "2" } }, undefined, { shallow: true });
    } catch (error) {
      const { message } = parseError(error);
      showToast({
        type: "error",
        message,
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
      // Never include `name` — API returns 422 NAME_NOT_UPDATABLE.
      // Read source (not refUrl) from GET; send as refUrl on write.
      const updateData: ModelUpdateRequest = {
        modelId: selectedModel.modelId,
        version: selectedModel.version,
        description: updateFormData.description,
        task: updateFormData.task,
        license: updateFormData.license as ModelUpdateRequest["license"],
        licenseUrl: updateFormData.licenseUrl ?? undefined,
        refUrl: updateFormData.source || undefined,
        domain: updateFormData.domain as ModelUpdateRequest["domain"],
        languages: updateFormData.languages,
        isLangDetectionEnabled: updateFormData.isLangDetectionEnabled,
        isMultilingual: updateFormData.isMultilingual,
        trainingDataset: updateFormData.trainingDataset ?? undefined,
        adapterConfig: updateFormData.adapterConfig ?? undefined,
        schema: updateFormData.schema ?? undefined,
      };

      await updateModel(updateData);

      showToast({
        type: "success",
        message: "Model has been updated successfully",
      });

      // Refresh models list and selected model
      await fetchModels();
      const updatedModel = await getModelById(selectedModel.modelId);
      setSelectedModel(updatedModel as unknown as Model);
      setUpdateFormData(updatedModel as unknown as Partial<Model>);
      setIsEditingModel(false);
    } catch (error) {
      const { message } = parseError(error);
      showToast({
        type: "error",
        message,
      });
    } finally {
      setIsUpdating(false);
    }
  };

  const handleDeprecateModel = async (model: Model) => {
    // Check session expiry before deprecating
    if (!checkSessionExpiry()) return;

    if (!model.modelId || !model.version) {
      showToast({
        type: "error",
        message: "Model ID and version are required",
      });
      return;
    }

    setUpdatingModelId(model.modelId);

    try {
      await updateModel({
        modelId: model.modelId,
        version: model.version,
        versionStatus: MODEL_VERSION.STATUS.DEPRECATED,
      });

      showToast({
        type: "success",
        message: `${model.name || model.modelId} has been deprecated successfully.`,
      });

      // Refresh models list and selected model
      await fetchModels();
      if (selectedModel && selectedModel.modelId === model.modelId) {
        const updatedModel = await getModelById(model.modelId);
        setSelectedModel(updatedModel as unknown as Model);
        setUpdateFormData(updatedModel as unknown as Partial<Model>);
      }
    } catch (error: any) {
      showError(error);
    } finally {
      setUpdatingModelId(null);
    }
  };

  const handleActivateModel = async (model: Model) => {
    // Check session expiry before activating
    if (!checkSessionExpiry()) return;

    if (!model.modelId || !model.version) {
      showToast({
        type: "error",
        message: "Model ID and version are required",
      });
      return;
    }

    setUpdatingModelId(model.modelId);

    try {
      await updateModel({
        modelId: model.modelId,
        version: model.version,
        versionStatus: MODEL_VERSION.STATUS.ACTIVE,
      });

      showToast({
        type: "success",
        message: `${model.name || model.modelId} has been activated successfully.`,
      });

      // Refresh models list and selected model
      await fetchModels();
      if (selectedModel && selectedModel.modelId === model.modelId) {
        const updatedModel = await getModelById(model.modelId);
        setSelectedModel(updatedModel as unknown as Model);
        setUpdateFormData(updatedModel as unknown as Partial<Model>);
      }
    } catch (error: any) {
      showError(error);
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

  const modelColumns = useMemo((): AdminTableColumn<Model>[] => {
    return [
      {
        id: "name",
        header: "Name",
        sortable: {
          label: "Name",
          direction: nameSortDirection,
          onAsc: () => {
            setSortBy("name");
            setNameSortDirection("asc");
          },
          onDesc: () => {
            setSortBy("name");
            setNameSortDirection("desc");
          },
          ascAriaLabel: "Sort models by name ascending",
          descAriaLabel: "Sort models by name descending",
        },
        cell: (model) => (
          <Text fontSize="sm" noOfLines={1} title={model.name}>
            {model.name}
          </Text>
        ),
      },
      {
        id: "version",
        header: "Version",
        cell: (model) => (
          <Text fontSize="sm" fontWeight="medium">
            {model.version || "1.0"}
          </Text>
        ),
      },
      {
        id: "status",
        header: "Status",
        cell: (model) => (
          <Badge
            colorScheme={isModelVersionStatusActive(model.versionStatus) ? "green" : "gray"}
            fontSize="xs"
          >
            {formatModelVersionStatusLabel(model.versionStatus)}
          </Badge>
        ),
      },
      {
        id: "task",
        header: "Task Type",
        cell: (model) => (
          <Badge colorScheme={getTaskColor(model.task.type)} fontSize="xs">
            {model.task.type.toUpperCase()}
          </Badge>
        ),
      },
      {
        id: "created",
        header: "Created At",
        cell: (model) => (
          <Text fontSize="sm" color="gray.600">
            {model.createdAt ? new Date(model.createdAt).toLocaleDateString() : "N/A"}
          </Text>
        ),
      },
      {
        id: "actions",
        header: "Actions",
        tdProps: { onClick: (e) => e.stopPropagation() },
        cell: (model) => (
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
            {!isRegistryReadOnly &&
              ((model.versionStatus?.toLowerCase() === "active" || !model.versionStatus) &&
              !modelIdsWithPublishedService.has(model.modelId) ? (
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
              ) : model.versionStatus?.toLowerCase() !== "active" && model.versionStatus ? (
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
              ) : null)}
          </HStack>
        ),
      },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nameSortDirection, modelIdsWithPublishedService, updatingModelId, isRegistryReadOnly]);

  return (
    <>
      <Head>
        <title>Model Management - AI4I Platform</title>
        <meta name="description" content="Manage and configure AI models" />
      </Head>

      <ContentLayout>
           <VStack spacing={6} w="full">
                  <ManagementPageHeader
                    title="Model Management"
                    description={
                      isRegistryReadOnly
                        ? "View models in the registry (read-only)"
                        : "Manage and configure AI models"
                    }
                  />

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
                if (isRegistryReadOnly && index === 1) return;
                setActiveTab(index);
                if (index !== viewTabIndex) {
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
                {!isRegistryReadOnly && (
                  <Tab fontWeight="semibold">Register Model</Tab>
                )}
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
                      <AdminDataTable
                        key={`${filterTaskType}-${filterVersionStatus}`}
                        items={registryTableItems}
                        columns={modelColumns}
                        getRowKey={(model) => model.modelId}
                        onRowClick={(model) => handleViewModel(model.modelId)}
                        paginate="client"
                        pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
                        isLoading={isLoading}
                        loadingMessage="Loading models..."
                        emptyMessage="No models in the registry yet."
                        noResultsMessage="No results found. Try adjusting your search or filters."
                        unfilteredCount={models.length}
                        hasActiveFilters={hasActiveFilters}
                        onClearFilters={clearAllFilters}
                        filters={
                          <VStack align="stretch" spacing={3} w="full">
                            <HStack flexWrap="wrap" spacing={3} align="flex-end">
                              <TableSearchField
                                label="Search"
                                value={searchQuery}
                                onChange={setSearchQuery}
                                placeholder="Search by model name..."
                                formControlProps={{ w: { base: "full", md: "280px" } }}
                              />
                              <TableSelectField
                                label="Status"
                                value={filterVersionStatus}
                                onChange={setFilterVersionStatus}
                                formControlProps={{ w: { base: "full", sm: "140px" } }}
                              >
                                <option value={MODEL_VERSION.FILTER.ALL}>All</option>
                                {MODEL_VERSION_FILTER_LIST.map((s) => (
                                  <option key={s} value={s}>
                                    {formatModelVersionFilterLabel(s)}
                                  </option>
                                ))}
                              </TableSelectField>
                              <TableSelectField
                                label="Task type"
                                value={filterTaskType}
                                onChange={setFilterTaskType}
                                formControlProps={{ w: { base: "full", sm: "160px" } }}
                              >
                                {taskTypeNames?.map((t) => (
                                  <option key={t} value={t}>
                                    {formatModelTaskTypeLabel(t)}
                                  </option>
                                ))}
                              </TableSelectField>
                            </HStack>
                            {hasActiveFilters && (
                              <HStack spacing={2} flexWrap="wrap">
                                {searchQuery.trim() && (
                                  <Badge
                                    colorScheme="blue"
                                    fontSize="xs"
                                    px={2}
                                    py={1}
                                    cursor="pointer"
                                    onClick={() => setSearchQuery("")}
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
                                    onClick={() => setFilterVersionStatus("")}
                                    _hover={{ opacity: 0.8 }}
                                  >
                                    Status: {formatModelVersionFilterLabel(filterVersionStatus)} ×
                                  </Badge>
                                )}
                              </HStack>
                            )}
                          </VStack>
                        }
                      />
                    </CardBody>
                  </Card>
                </TabPanel>

                {/* Create Model Tab */}
                {!isRegistryReadOnly && (
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
                                Required Fields (ULCA):
                              </Text>
                              <Text fontSize="xs" color="blue.600">
                                name (5–100 chars, no spaces), version, description (25–1000 chars),
                                task.type, license (closed enum), domain (closed enum, ≥1),
                                trainingDataset.{"{description}"},
                                submitter.name. Optional: refUrl, languages (Indic + English codes only),
                                licenseUrl, isLangDetectionEnabled, isMultilingual,
                                adapterConfig, schema, benchmarks.
                                modelId is auto-generated from name:version. Do not send submittedOn/updatedOn
                                unless you intend to override — they are server-set by default.
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
                )}

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
                            (selectedModel.versionStatus?.toLowerCase() === "active" || !selectedModel.versionStatus) && !modelIdsWithPublishedService.has(selectedModel.modelId) ? (
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
                                  colorScheme={
                                    isModelVersionStatusActive(selectedModel.versionStatus)
                                      ? "green"
                                      : "gray"
                                  }
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
                              {selectedModel.licenseUrl ? (
                                <Box>
                                  <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                                    License URL
                                  </Text>
                                  <Text fontSize="md">{selectedModel.licenseUrl}</Text>
                                </Box>
                              ) : null}
                              <Box>
                                <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                                  Language auto-detection
                                </Text>
                                <Text fontSize="md">
                                  {selectedModel.isLangDetectionEnabled ? "Enabled" : "Disabled"}
                                </Text>
                              </Box>
                              <Box>
                                <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                                  Multilingual
                                </Text>
                                <Text fontSize="md">
                                  {selectedModel.isMultilingual ? "Yes" : "No"}
                                </Text>
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

                            {selectedModel.trainingDataset ? (
                              <Box>
                                <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                                  Training dataset
                                </Text>
                                <Text fontSize="md">
                                  {selectedModel.trainingDataset.description || "—"}
                                </Text>
                                {selectedModel.trainingDataset.datasetId ? (
                                  <Text fontSize="sm" color="gray.500" mt={1}>
                                    ID: {selectedModel.trainingDataset.datasetId}
                                  </Text>
                                ) : null}
                              </Box>
                            ) : null}

                            {selectedModel.adapterConfig ? (
                              <Box>
                                <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                                  Adapter config
                                </Text>
                                <Text fontSize="sm" fontFamily="mono" whiteSpace="pre-wrap">
                                  {JSON.stringify(selectedModel.adapterConfig, null, 2)}
                                </Text>
                              </Box>
                            ) : null}

                            {selectedModel.schema ? (
                              <Box>
                                <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                                  Schema
                                </Text>
                                <Text fontSize="sm" fontFamily="mono" whiteSpace="pre-wrap">
                                  {JSON.stringify(selectedModel.schema, null, 2)}
                                </Text>
                              </Box>
                            ) : null}
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
