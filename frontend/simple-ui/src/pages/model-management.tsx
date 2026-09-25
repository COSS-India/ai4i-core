// Model Management page with list and create functionality

import {
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  FormControl,
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
  Alert,
  AlertIcon,
  AlertDescription,
  Code,
  Spinner,
  Center,
  Tooltip,
} from "@chakra-ui/react";
import Head from "next/head";
import { CopyIcon } from "@chakra-ui/icons";
import { useRouter } from "next/router";
import React, { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import ContentLayout from "../components/common/ContentLayout";
import FieldHint from "../components/common/FieldHint";
import FieldLabel from "../components/common/FieldLabel";
import { FIELD_HINTS } from "../config/fieldHints";
import ManagementPageHeader from "../components/common/ManagementPageHeader";
import CreateButton from "../components/common/CreateButton";
import FormActions from "../components/common/FormActions";
import { CreateModal } from "../components/common/StandardModal";
import FormSection from "../components/common/FormSection";
import ModelExtraDetails from "../components/model-management/ModelDetails";
import ModelForm from "../components/model-management/ModelForm";
import ModelReview from "../components/model-management/ModelReview";
import {
  fetchAllModelsMatchingFilters,
  createModel,
  getModelById,
  updateModel,
  MODELS_ALL_QUERY_KEY,
} from "../services/modelManagementService";
import type { ModelCreateRequest, ModelDetails } from "../types/platform";
import {
  listServices as listServicesForModels,
  SERVICES_ALL_QUERY_KEY,
  SERVICES_ALL_STALE_MS,
} from "../services/servicesManagementService";
import { useAuth } from "../hooks/useAuth";
import { isRegistryReadOnlyUser, userHasRole } from "../utils/rbac";
import { useSessionExpiry } from "../hooks/useSessionExpiry";
import { parseError, showError } from "../utils/errorHandler";
import { SAMPLE_MODEL_JSON } from "../utils/sampleModelJson";
import { stripJsonComments } from "../utils/stripJsonComments";
import { showToast } from "../utils/toast";
import { useCopyToClipboard } from "../hooks/useCopyToClipboard";
import ConfirmDialog from "../components/common/ConfirmDialog";
import DataTable, {
  useAdminTableSurface,
  DEFAULT_PAGE_SIZE_OPTIONS,
  type DataTableColumn,
} from "../components/common/table";
import { useDeferredColumnSort } from "../utils/tableSort";
import {
  MODEL_VERSION,
  MODEL_VERSION_FILTER_LIST,
  MODEL_FIELD_LIMITS,
  MODEL_API_KEY_REDACTED,
  formatModelTaskTypeLabel,
  getTaskColorScheme,
  formatModelVersionFilterLabel,
  formatModelVersionStatusLabel,
  isModelVersionStatusActive,
} from "../config/constants";
import { useInferenceTypes } from "../hooks/useInferenceTypes";
import { getPlatformName } from "../config/runtimeConfig";
import { resolveTaskType } from "../utils/platformService";

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
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState(0);
  const [uploadedModelData, setUploadedModelData] = useState<any>(null);
  const [parsedModelData, setParsedModelData] = useState<any>(null);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [updatingModelId, setUpdatingModelId] = useState<string | null>(null);
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
    // Single enabled type → lock filter to it (no All). Multiple → default All ("").
    if (taskTypeNames.length === 1) setFilterTaskType(taskTypeNames[0]);
    setTaskTypeFilterReady(true);
  }, [isLoadingTaskTypes, taskTypeNames]);
  const modelSortAccessors = useMemo(
    () => ({
      name: (m: Model) => m.name ?? "",
      version: (m: Model) => m.version ?? "",
      created: (m: Model) => {
        if (m.createdAt != null) return new Date(m.createdAt).getTime();
        if (m.submittedOn != null) return m.submittedOn * 1000;
        return 0;
      },
    }),
    [],
  );
  const modelSort = useDeferredColumnSort("name", modelSortAccessors);
  const { isOpen: isConfirmOpen, onOpen: onConfirmOpen, onClose: onConfirmClose } = useDisclosure();
  const cancelConfirmRef = React.useRef<HTMLButtonElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const isRegistryReadOnly = isRegistryReadOnlyUser(user?.roles);
  const viewTabIndex = 1;
  const { isOpen: isCreateOpen, onOpen: onCreateOpen, onClose: onCreateCloseRaw } = useDisclosure();
  const { copy } = useCopyToClipboard();

  const { checkSessionExpiry } = useSessionExpiry();
  const router = useRouter();

  // Check if user is GUEST or USER and redirect if so
  useEffect(() => {
    if (userHasRole(user?.roles, "GUEST") || userHasRole(user?.roles, "USER")) {
      showToast({
        type: "error",
        message: "You do not have access to Model Management.",
      });
      router.push('/');
    }
  }, [user, router]);

  // Sync URL tab param. ?tab=1 and ?tab=create open CreateModal (legacy create-tab links).
  useEffect(() => {
    const t = router.query.tab;
    if (t === "1" || t === "create") {
      if (isRegistryReadOnly) {
        setActiveTab(0);
      } else {
        onCreateOpen();
      }
      if (router.query.tab) {
        const q = { ...router.query } as Record<string, string>;
        delete q.tab;
        router.replace({ pathname: "/model-management", query: q }, undefined, { shallow: true });
      }
      return;
    }
    if (t === "2") setActiveTab(viewTabIndex);
    else setActiveTab(0);
  }, [router.query.tab, isRegistryReadOnly, router, viewTabIndex, onCreateOpen]);

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

  const { data: allServices } = useQuery({
    queryKey: SERVICES_ALL_QUERY_KEY,
    queryFn: listServicesForModels,
    staleTime: SERVICES_ALL_STALE_MS,
  });
  const modelIdsWithPublishedService = useMemo(() => {
    const ids = new Set<string>();
    (allServices || []).forEach((s: { modelId?: string; model_id?: string; isPublished?: boolean; is_published?: boolean }) => {
      const id = s.modelId ?? s.model_id;
      const published = s.isPublished === true || s.is_published === true;
      if (id && published) ids.add(String(id));
    });
    return ids;
  }, [allServices]);

  const { cardBg, borderColor: cardBorder } = useAdminTableSurface();

  // Client-side name filter + multi-column sort over the full fetched registry list.
  const registryTableItems = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const filtered = q
      ? models.filter((m) => (m.name ?? "").toLowerCase().includes(q))
      : models;
    return modelSort.apply(filtered);
  }, [models, searchQuery, modelSort]);

  const showTaskTypeAllOption = taskTypeNames.length > 1;
  const hasActiveFilters =
    filterVersionStatus !== "" ||
    (showTaskTypeAllOption && filterTaskType !== "") ||
    searchQuery.trim() !== "";
  const clearAllFilters = () => {
    setSearchQuery("");
    setFilterVersionStatus("");
    setFilterTaskType(taskTypeNames.length === 1 ? taskTypeNames[0] : "");
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

  const closeCreateModal = () => {
    handleClearUpload();
    onCreateCloseRaw();
  };

  const openCreateModal = () => {
    handleClearUpload();
    onCreateOpen();
  };

  const handleDownloadSample = () => {
    const blob = new Blob([SAMPLE_MODEL_JSON], { type: "application/json" });
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

    if (data.adapterConfig != null) {
      if (typeof data.adapterConfig !== "object" || Array.isArray(data.adapterConfig)) {
        errors.push("adapterConfig must be an object when provided");
      } else {
        if (!Array.isArray((data.adapterConfig as Record<string, unknown>).inputs)) {
          errors.push("adapterConfig.inputs is required and must be an array");
        }
        if (!Array.isArray((data.adapterConfig as Record<string, unknown>).outputs)) {
          errors.push("adapterConfig.outputs is required and must be an array");
        }
      }
    }

    if (data.schema != null) {
      if (typeof data.schema !== "object" || Array.isArray(data.schema)) {
        errors.push("schema must be an object when provided");
      } else if (!(data.schema as Record<string, unknown>).model_name) {
        errors.push("schema.model_name is required");
      }
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
      void queryClient.invalidateQueries({ queryKey: MODELS_ALL_QUERY_KEY });

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

      // Parse JSON — comments from the annotated sample file are stripped first.
      // stripJsonComments preserves line breaks, so the position the parser reports
      // refers to the same line in the file the user edited.
      let parsedData: any;
      try {
        parsedData = JSON.parse(stripJsonComments(fileContent));
      } catch (jsonError: any) {
        const detail = jsonError?.message ? ` ${jsonError.message}` : '';
        throw new Error(`Invalid JSON format. Please check your file.${detail}`);
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
        message: "JSON file has been validated successfully. Review the data below and click 'Create Model' to proceed.",
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
      void queryClient.invalidateQueries({ queryKey: MODELS_ALL_QUERY_KEY });
      if (selectedModel && selectedModel.modelId === model.modelId) {
        const updatedModel = await getModelById(model.modelId);
        setSelectedModel(updatedModel as unknown as Model);
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
      void queryClient.invalidateQueries({ queryKey: MODELS_ALL_QUERY_KEY });
      if (selectedModel && selectedModel.modelId === model.modelId) {
        const updatedModel = await getModelById(model.modelId);
        setSelectedModel(updatedModel as unknown as Model);
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

  const modelColumns = useMemo((): DataTableColumn<Model>[] => {
    return [
      {
        id: "name",
        header: "Name",
        sortable: true,
        sortAccessor: (model) => model.name ?? "",
        cell: (model) => (
          <Text fontWeight="medium" fontSize="sm" noOfLines={1} title={model.name || model.modelId}>
            {model.name || model.modelId || "—"}
          </Text>
        ),
      },
      {
        id: "version",
        header: "Version",
        sortable: true,
        sortAccessor: (model) => model.version ?? "",
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
        cell: (model) => {
          const taskType = resolveTaskType(model);
          return (
            <Badge colorScheme={getTaskColorScheme(taskType)} fontSize="xs">
              {taskType ? taskType.toUpperCase() : "N/A"}
            </Badge>
          );
        },
      },
      {
        id: "created",
        header: "Created At",
        sortable: true,
        sortAccessor: (model) => {
          if (model.createdAt != null) return new Date(model.createdAt).getTime();
          if (model.submittedOn != null) return model.submittedOn * 1000;
          return 0;
        },
        cell: (model) => {
          const createdMs =
            model.createdAt != null
              ? new Date(model.createdAt).getTime()
              : model.submittedOn != null
                ? model.submittedOn * 1000
                : NaN;
          return (
            <Text fontSize="sm" color="ink.600">
              {Number.isFinite(createdMs) ? new Date(createdMs).toLocaleDateString() : "N/A"}
            </Text>
          );
        },
      },
      {
        id: "actions",
        header: "Actions",
        tdProps: { onClick: (e) => e.stopPropagation() },
        cell: (model) => (
          <HStack spacing={3} align="center">
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
  }, [modelSort, modelIdsWithPublishedService, updatingModelId, isRegistryReadOnly]);

  return (
    <>
      <Head>
        <title>{`Model Management - ${getPlatformName()}`}</title>
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
                    actions={
                      !isRegistryReadOnly ? (
                        <CreateButton onClick={openCreateModal}>Create Model</CreateButton>
                      ) : undefined
                    }
                  />

                    <Tabs
              colorScheme="blue"
              variant="enclosed"
              index={activeTab}
              onChange={(index) => {
                setActiveTab(index);
                if (index !== viewTabIndex) {
                  setIsViewingModel(false);
                  setSelectedModel(null);
                }
                const q = { ...router.query } as Record<string, string>;
                if (index === 0) delete q.tab;
                else q.tab = "2";
                router.replace({ pathname: "/model-management", query: q }, undefined, { shallow: true });
              }}
            >
              <TabList>
                <Tab fontWeight="semibold">Model Registry</Tab>
                {isViewingModel && selectedModel && (
                  <Tab fontWeight="semibold">View Model</Tab>
                )}
              </TabList>

              <TabPanels>
                {/* Model Registry Tab */}
                <TabPanel px={0} pt={6}>
                      <DataTable
                        layout="admin"
                        key={`${filterTaskType}-${filterVersionStatus}`}
                        items={registryTableItems}
                        columns={modelColumns}
            sort={modelSort.sort}
            onSortChange={modelSort.onSortChange}
                        getRowKey={(model) => model.modelId}
                        onRowClick={(model) => handleViewModel(model.modelId)}
                        paginate="client"
                        paginationPosition="bottom"
                        pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
                        isLoading={isLoading}
                        loadingMessage="Loading models..."
                        emptyMessage="No models in the registry yet."
                        noResultsMessage="No results found. Try adjusting your search or filters."
                        unfilteredCount={models.length}
                        hasActiveFilters={hasActiveFilters}
                        onClearFilters={clearAllFilters}
                        search={{
                          label: "Search",
                          value: searchQuery,
                          onChange: setSearchQuery,
                          placeholder: "Search by model name...",
                          fields: ["model_name", "name"],
                        }}
                        filterDefs={[
                          {
                            id: "status",
                            label: "Status",
                            type: "select",
                            param: "version_status",
                            value: filterVersionStatus,
                            onChange: setFilterVersionStatus,
                            width: { base: "full", sm: "140px" },
                            options: [
                              { label: "All", value: MODEL_VERSION.FILTER.ALL },
                              ...MODEL_VERSION_FILTER_LIST.map((s) => ({
                                label: formatModelVersionFilterLabel(s),
                                value: s,
                              })),
                            ],
                          },
                          {
                            id: "taskType",
                            label: "Task type",
                            type: "select",
                            param: "model_task_type",
                            value: filterTaskType,
                            onChange: setFilterTaskType,
                            width: { base: "full", sm: "160px" },
                            options: [
                              ...(showTaskTypeAllOption
                                ? [{ label: "All", value: "" }]
                                : []),
                              ...taskTypeNames.map((t) => ({
                                label: formatModelTaskTypeLabel(t),
                                value: t,
                              })),
                            ],
                          },
                        ]}
                      />
                </TabPanel>

                {/* View Model Tab */}
                {isViewingModel && selectedModel && (
                  <TabPanel px={0} pt={6}>
                    <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
                      <CardHeader>
                        <HStack justify="space-between" align="center">
                          <Heading size="md" color="ink.800" userSelect="none" cursor="default">
                           {selectedModel.name}
                          </Heading>
                          <HStack spacing={2}>
                            {!isRegistryReadOnly &&
                              (selectedModel.versionStatus?.toLowerCase() === "active" || !selectedModel.versionStatus) && (
                              <CreateButton
                                size="sm"
                                onClick={() => {
                                  router.push(
                                    `/services-management?modelId=${selectedModel.modelId}&tab=create`,
                                  );
                                }}
                              >
                                Create Service
                              </CreateButton>
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
                          <VStack spacing={6} align="stretch">
                            {isRegistryReadOnly && (
                              <Badge colorScheme="gray" alignSelf="flex-start" fontSize="sm" px={2} py={1}>
                                Read-only
                              </Badge>
                            )}
                            <ModelForm mode="view" model={selectedModel} />
                            <ModelExtraDetails
                              trainingDataset={selectedModel.trainingDataset}
                              adapterConfig={selectedModel.adapterConfig}
                              schema={selectedModel.schema}
                            />
                          </VStack>
                      </CardBody>
                    </Card>
                  </TabPanel>
                )}
              </TabPanels>
            </Tabs>
     </VStack>
      </ContentLayout>

      {!isRegistryReadOnly && (
        <CreateModal
          isOpen={isCreateOpen}
          onClose={closeCreateModal}
          size="lg"
          title="Create Model"
          description="Upload a model definition to add it to the registry."
          footer={
            <FormActions
              submitLabel="Create Model"
              onCancel={closeCreateModal}
              onSubmit={() => void handleCreateModel()}
              isLoading={isUploading}
              loadingText="Creating..."
              isDisabled={!parsedModelData}
              justify="space-between"
              pt={0}
            />
          }
        >
          <VStack spacing={6} align="stretch">
            <FormSection title="Upload Model Definition">
            <Box>
              <FormControl>
                <HStack justify="space-between" mb={2}>
                  <FieldLabel formLabelProps={{ fontWeight: "semibold", mb: 0 }}>
                    Upload JSON File
                  </FieldLabel>
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
                <FieldHint mt={2} fontSize="sm">
                  {FIELD_HINTS.model.jsonUpload.helper}
                </FieldHint>
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
            </FormSection>

            {isValidating && (
              <Center py={8}>
                <VStack spacing={4}>
                  <Spinner size="lg" />
                  <Text color="ink.600">Validating JSON file...</Text>
                </VStack>
              </Center>
            )}

            {isUploading && (
              <Center py={8}>
                <VStack spacing={4}>
                  <Spinner size="lg" />
                  <Text color="ink.600">Creating model...</Text>
                </VStack>
              </Center>
            )}

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

            {parsedModelData && !isUploading && !isValidating && (
              <Box>
                <Alert status="success" borderRadius="md" mb={4}>
                  <AlertIcon />
                  <AlertDescription>
                    JSON file validated successfully! Review the data below and click &quot;Create Model&quot; to proceed.
                  </AlertDescription>
                </Alert>
                <FormSection title="Review Model">
                  <VStack align="stretch" spacing={6}>
                    <ModelReview model={parsedModelData} />
                    <ModelExtraDetails
                      trainingDataset={parsedModelData.trainingDataset}
                      adapterConfig={parsedModelData.adapterConfig}
                      schema={parsedModelData.schema}
                    />
                  </VStack>
                </FormSection>
              </Box>
            )}

            {uploadedModelData && !isUploading && (
              <Box>
                <Alert status="success" borderRadius="md" mb={4}>
                  <AlertIcon />
                  <AlertDescription>
                    Model created successfully! Model data is displayed below. Copy it if you need a record — the modal stays open until you close it.
                  </AlertDescription>
                </Alert>
                <HStack justify="space-between" align="center" mb={4}>
                  <Heading size="sm" color="ink.700" userSelect="none" cursor="default">
                    Created Model Data
                  </Heading>
                  <Button
                    size="sm"
                    variant="outline"
                    leftIcon={<CopyIcon />}
                    onClick={() => {
                      void copy(
                        JSON.stringify(uploadedModelData, null, 2),
                        "Model data copied to clipboard",
                      );
                    }}
                  >
                    Copy
                  </Button>
                </HStack>
                <Box
                  bg="ink.50"
                  p={4}
                  borderRadius="md"
                  border="1px solid"
                  borderColor="ink.200"
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
            )}
          </VStack>
        </CreateModal>
      )}

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
