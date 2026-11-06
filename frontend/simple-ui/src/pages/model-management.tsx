// Model Management page with list and create functionality

import {
  Badge,
  Box,
  HStack,
  Skeleton,
  Switch,
  Text,
  useDisclosure,
  Tooltip,
} from "@chakra-ui/react";
import Head from "next/head";
import { useRouter } from "next/router";
import React, { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import ContentLayout from "../components/common/ContentLayout";
import ManagementPageHeader from "../components/common/ManagementPageHeader";
import CreateButton from "../components/common/CreateButton";
import FormActions from "../components/common/FormActions";
import FormDrawer from "../components/common/FormDrawer";
import ModelExtraDetails from "../components/model-management/ModelDetails";
import ModelForm from "../components/model-management/ModelForm";
import ModelListColumnPicker from "../components/model-management/ModelListColumnPicker";
import { validateModelData } from "../components/model-management/modelJsonValidation";
import {
  modelCreatedAtMs,
  renderModelCreatedAtCell,
  renderModelNameCell,
  renderModelProviderCell,
  renderModelStatusCell,
  renderModelTaskTypeCell,
  renderModelVersionCell,
  modelListColumnWidth,
} from "../components/model-management/modelListCells";
import { modelListColumnsParam } from "../components/model-management/modelListColumns";
import { useModelRegistryList } from "../components/model-management/useModelRegistryList";
import { useModelListColumnCatalogue } from "../components/model-management/useModelListColumnCatalogue";
import { useModelListVisibleColumns } from "../components/model-management/useModelListVisibleColumns";
import {
  createModel,
  getModelById,
  updateModel,
  MODELS_ALL_QUERY_KEY,
  MODEL_LIST_QUERY_KEY,
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
import { MODEL_SAMPLES, type ModelSampleKind } from "../utils/sampleModelJson";
import { stripJsonComments } from "../utils/stripJsonComments";
import { showToast } from "../utils/toast";
import { useCopyToClipboard } from "../hooks/useCopyToClipboard";
import ConfirmDialog from "../components/common/ConfirmDialog";
import DataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  actionsColumnSize,
  type DataTableColumn,
} from "../components/common/table";
import { FIELD_HINTS } from "../config/fieldHints";
import { useDeferredColumnSort } from "../utils/tableSort";
import {
  MODEL_VERSION,
  MODEL_VERSION_FILTER_LIST,
  MODEL_API_KEY_REDACTED,
  formatModelTaskTypeLabel,
  formatModelVersionFilterLabel,
} from "../config/constants";
import { useInferenceTypes } from "../hooks/useInferenceTypes";
import { getPlatformName } from "../config/runtimeConfig";

/** Right-align Actions-column content without nesting a helper inside `cell`. */
function modelActionsRail(child: React.ReactNode): React.ReactElement {
  return (
    <Box
      display="flex"
      justifyContent="flex-end"
      alignItems="center"
      w="100%"
      minH="32px"
    >
      {child}
    </Box>
  );
}

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

/** Rows arrive sorted from GET /models/list; the sort hook only tracks the header state. */
const NO_CLIENT_SORT_ACCESSORS: Record<string, (row: Model) => string | number> = {};

const ModelManagementPage: React.FC = () => {
  const [selectedModel, setSelectedModel] = useState<Model | null>(null);
  const [isViewingModel, setIsViewingModel] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [uploadedModelData, setUploadedModelData] = useState<any>(null);
  const [parsedModelData, setParsedModelData] = useState<any>(null);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [updatingModelId, setUpdatingModelId] = useState<string | null>(null);
  const [modelToConfirm, setModelToConfirm] = useState<Model | null>(null);
  const [confirmAction, setConfirmAction] = useState<"deprecate" | "activate" | null>(null);
  const { taskTypeNames, isLoading: isLoadingTaskTypes } = useInferenceTypes();
  // GET /models/list sorts; no column picked → API default (newest first).
  const modelSort = useDeferredColumnSort("name", NO_CLIENT_SORT_ACCESSORS);
  const { isOpen: isConfirmOpen, onOpen: onConfirmOpen, onClose: onConfirmClose } = useDisclosure();
  const cancelConfirmRef = React.useRef<HTMLButtonElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  /** Model id already applied from `?modelId=` (Create Service Cancel). */
  const loadedReturnModelIdRef = useRef<string | null>(null);
  /** Bumped when the user leaves or opens a row, so a late return fetch cannot reopen. */
  const modelReturnGenRef = useRef(0);
  const { user } = useAuth();
  const { catalogue: modelListColumns, isLoading: isLoadingColumns } =
    useModelListColumnCatalogue();
  const {
    visibleColumnIds,
    visibleColumnsReady,
    applyVisibleColumns,
    resetVisibleColumns,
  } = useModelListVisibleColumns({
    userId: user?.user_id ?? "",
    catalogue: modelListColumns,
    modelSort,
  });
  const queryClient = useQueryClient();
  const isRegistryReadOnly = isRegistryReadOnlyUser(user?.roles);
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
      if (!isRegistryReadOnly) {
        onCreateOpen();
      }
      if (router.query.tab) {
        const q = { ...router.query } as Record<string, string>;
        delete q.tab;
        router.replace({ pathname: "/model-management", query: q }, undefined, { shallow: true });
      }
    }
  }, [router.query.tab, isRegistryReadOnly, router, onCreateOpen]);

  // Explicit return from another workflow (Create Service Cancel). Not history back.
  // modelId stays in the URL so refresh reopens this model. Row-open views do not use it.
  useEffect(() => {
    const raw = router.query.modelId;
    if (typeof raw !== "string" || !raw) return;
    if (loadedReturnModelIdRef.current === raw) return;
    if (!checkSessionExpiry()) return;

    const gen = modelReturnGenRef.current;
    const queryAtStart = { ...router.query } as Record<string, string>;
    loadedReturnModelIdRef.current = raw;
    let settled = false;
    let cancelled = false;
    (async () => {
      try {
        const model = await getModelById(raw);
        if (cancelled || gen !== modelReturnGenRef.current) return;
        settled = true;
        setSelectedModel(model as unknown as Model);
        setIsViewingModel(true);
        if (queryAtStart.tab === "2") return;
        router.replace(
          {
            pathname: "/model-management",
            query: { ...queryAtStart, modelId: raw, tab: "2" },
          },
          undefined,
          { shallow: true },
        );
      } catch (error) {
        if (cancelled || gen !== modelReturnGenRef.current) return;
        settled = true;
        loadedReturnModelIdRef.current = null;
        const { message } = parseError(error);
        showToast({ type: "error", message });
      }
    })();
    return () => {
      cancelled = true;
      if (!settled && loadedReturnModelIdRef.current === raw) {
        loadedReturnModelIdRef.current = null;
      }
    };
    // Re-run only when the return id changes. `router` identity must not refetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router.query.modelId]);

  // Like Services Management: GET /models/list does the search, sort and paging,
  // and `columns=` limits each row to the visible columns' fields.
  const modelColumnsParam = useMemo(
    () => modelListColumnsParam(visibleColumnIds),
    [visibleColumnIds],
  );
  const registry = useModelRegistryList({
    columns: modelColumnsParam,
    enabledTaskTypes: taskTypeNames,
    modelSort,
    // Wait for the saved selection so the first request never sends the fallback ids.
    enabled: !isLoadingTaskTypes && visibleColumnsReady,
  });
  const registryItems = registry.items as unknown as Model[];
  const refreshModels = useCallback(async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: MODEL_LIST_QUERY_KEY }),
      // Services Management keeps its own full-row copy.
      queryClient.invalidateQueries({ queryKey: MODELS_ALL_QUERY_KEY }),
    ]);
  }, [queryClient]);

  // Wait for the column config so the table does not swap columns after first paint.
  const isLoading = registry.isLoading || isLoadingColumns || !visibleColumnsReady;

  const {
    data: allServices,
    isPending: isServicesPending,
    isError: isServicesError,
  } = useQuery({
    queryKey: SERVICES_ALL_QUERY_KEY,
    queryFn: listServicesForModels,
    staleTime: SERVICES_ALL_STALE_MS,
  });
  /** Counts are unknown, not zero, until the services list resolves. */
  const isServiceCountLoading = isServicesPending;
  const hasServiceCountError = isServicesError;

  /** Service counts per model from the existing services list (FE-owned). */
  const serviceCountByModelId = useMemo(() => {
    const counts = new Map<string, number>();
    (allServices || []).forEach(
      (s: { modelId?: string; model_id?: string }) => {
        const id = s.modelId ?? s.model_id;
        if (!id) return;
        const key = String(id);
        counts.set(key, (counts.get(key) ?? 0) + 1);
      },
    );
    return counts;
  }, [allServices]);

  /** Models that have at least one published service (BE rejects deprecate with 409). */
  const modelIdsWithPublishedService = useMemo(() => {
    const ids = new Set<string>();
    (allServices || []).forEach(
      (s: {
        modelId?: string;
        model_id?: string;
        isPublished?: boolean;
        is_published?: boolean;
      }) => {
        const id = s.modelId ?? s.model_id;
        const published = s.isPublished === true || s.is_published === true;
        if (id && published) ids.add(String(id));
      },
    );
    return ids;
  }, [allServices]);

  const getServiceCount = useCallback(
    (model: Model): number => serviceCountByModelId.get(model.modelId) ?? 0,
    [serviceCountByModelId],
  );

  const hasLinkedServices = useCallback(
    (model: Model) => getServiceCount(model) > 0,
    [getServiceCount],
  );

  const hasPublishedService = useCallback(
    (model: Model) => modelIdsWithPublishedService.has(model.modelId),
    [modelIdsWithPublishedService],
  );

  const isModelActive = useCallback((model: Model) => {
    return (
      model.versionStatus?.toLowerCase() === "active" || !model.versionStatus
    );
  }, []);

  const isModelDeprecated = useCallback((model: Model) => {
    return Boolean(
      model.versionStatus && model.versionStatus.toLowerCase() !== "active",
    );
  }, []);

  const showTaskTypeAllOption = taskTypeNames.length > 1;
  // One enabled task type: the toolbar shows it picked (no All), like before.
  const toolbarTaskType =
    registry.filters.taskType ?? (showTaskTypeAllOption ? "" : taskTypeNames[0] ?? "");

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
    modelReturnGenRef.current += 1;
    handleClearUpload();
    onCreateOpen();
  };

  const handleDownloadSample = (kind: ModelSampleKind) => {
    const sample = MODEL_SAMPLES[kind];
    const blob = new Blob([sample.json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = sample.fileName;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
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
      await refreshModels();

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

    modelReturnGenRef.current += 1;
    loadedReturnModelIdRef.current = null;
    try {
      const model = await getModelById(modelId);
      setSelectedModel(model as unknown as Model);
      setIsViewingModel(true);
      const q = { ...router.query } as Record<string, string>;
      delete q.modelId;
      q.tab = "2";
      router.replace({ pathname: "/model-management", query: q }, undefined, { shallow: true });
    } catch (error) {
      const { message } = parseError(error);
      showToast({
        type: "error",
        message,
      });
    }
  };

  const closeModelView = () => {
    modelReturnGenRef.current += 1;
    loadedReturnModelIdRef.current = null;
    setIsViewingModel(false);
    setSelectedModel(null);
    const q = { ...router.query } as Record<string, string>;
    delete q.tab;
    delete q.modelId;
    router.replace({ pathname: "/model-management", query: q }, undefined, { shallow: true });
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
      await refreshModels();
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
      await refreshModels();
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

  const modelColumnTemplates = useMemo((): DataTableColumn<Model>[] => {
    return [
      {
        id: "name",
        header: "Name",
        sortable: true,
        sortAccessor: (model) => model.name ?? "",
        cell: renderModelNameCell,
      },
      {
        id: "version",
        header: "Version",
        sortable: true,
        sortAccessor: (model) => model.version ?? "",
        cell: renderModelVersionCell,
      },
      {
        id: "taskType",
        header: "Task Type",
        hint: FIELD_HINTS.model.col.task,
        cell: renderModelTaskTypeCell,
      },
      {
        id: "providerName",
        header: "Provider Name",
        hint: FIELD_HINTS.model.col.provider,
        sortable: true,
        sortAccessor: (model) => model.providerName ?? model.submitter?.name ?? "",
        cell: renderModelProviderCell,
      },
      {
        id: "status",
        header: "Status",
        hint: FIELD_HINTS.model.col.status,
        cell: renderModelStatusCell,
      },
      {
        id: "createdAt",
        header: "Created At",
        sortable: true,
        sortAccessor: (model) => {
          const ms = modelCreatedAtMs(model);
          return Number.isFinite(ms) ? ms : 0;
        },
        cell: renderModelCreatedAtCell,
      },
      {
        id: "noOfServices",
        header: "No. of Services",
        hint: FIELD_HINTS.model.col.services,
        cell: (model) => {
          if (isServiceCountLoading) {
            return <Skeleton height="20px" width="28px" borderRadius="md" />;
          }
          if (hasServiceCountError) {
            return (
              <Tooltip label="Could not load services" placement="top" hasArrow>
                <Text fontSize="sm" color="gray.400">
                  —
                </Text>
              </Tooltip>
            );
          }
          const count = getServiceCount(model);
          return (
            <Text fontSize="sm" color="ink.600">
              {count > 0 ? count : "-"}
            </Text>
          );
        },
      },
      {
        id: "actions",
        header: "Actions",
        align: "right" as const,
        truncate: false,
        ...actionsColumnSize(1),
        thProps: { textAlign: "right", whiteSpace: "nowrap", px: 2, overflow: "visible" },
        tdProps: {
          onClick: (e) => e.stopPropagation(),
          textAlign: "right",
          px: 2,
        },
        cell: (model) => {
          if (isServiceCountLoading) {
            return modelActionsRail(
              <Skeleton height="20px" width="36px" borderRadius="md" />,
            );
          }
          if (hasServiceCountError) {
            return modelActionsRail(
              <Tooltip label="Could not load services" placement="top" hasArrow>
                <Text fontSize="sm" color="gray.400">
                  —
                </Text>
              </Tooltip>,
            );
          }

          // Deprecated models must stay activatable even with 0 services
          // (Create Service is hidden for deprecated models).
          if (!isRegistryReadOnly && isModelDeprecated(model)) {
            return modelActionsRail(
              <Tooltip label="Activate model" placement="top" hasArrow>
                <Box as="span" display="inline-flex" alignItems="center">
                  <Switch
                    size="md"
                    colorScheme="green"
                    isChecked={false}
                    cursor="pointer"
                    onChange={() => openConfirmDialog("activate", model)}
                    isDisabled={updatingModelId !== null}
                    onClick={(e) => e.stopPropagation()}
                  />
                </Box>
              </Tooltip>,
            );
          }

          if (isModelActive(model) && !hasLinkedServices(model)) {
            return modelActionsRail(
              <Text fontSize="sm" color="ink.600">
                NA
              </Text>,
            );
          }

          if (isRegistryReadOnly || !isModelActive(model)) {
            return modelActionsRail(null);
          }

          const blockedByPublished = hasPublishedService(model);
          return modelActionsRail(
            <Tooltip
              label={
                blockedByPublished
                  ? "Unpublish its services to deprecate"
                  : "Deprecate model"
              }
              placement="top"
              hasArrow
            >
              <Box as="span" display="inline-flex" alignItems="center">
                <Switch
                  size="md"
                  colorScheme="green"
                  isChecked={true}
                  cursor="pointer"
                  onChange={() => {
                    if (blockedByPublished) return;
                    openConfirmDialog("deprecate", model);
                  }}
                  isDisabled={updatingModelId !== null || blockedByPublished}
                  onClick={(e) => e.stopPropagation()}
                />
              </Box>
            </Tooltip>,
          );
        },
      },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    modelSort,
    getServiceCount,
    hasLinkedServices,
    hasPublishedService,
    isModelActive,
    isModelDeprecated,
    isServiceCountLoading,
    hasServiceCountError,
    updatingModelId,
    isRegistryReadOnly,
  ]);

  const modelColumns = useMemo((): DataTableColumn<Model>[] => {
    // Headers come from the `model-column` config labels.
    const labels = new Map(modelListColumns.map((column) => [column.id, column.label]));
    const byId = new Map(
      modelColumnTemplates.map((col) => [
        col.id,
        {
          ...col,
          ...modelListColumnWidth(col.id),
          header: labels.get(col.id) ?? col.header,
        },
      ]),
    );
    const visible = visibleColumnIds
      .map((id) => byId.get(id))
      .filter((col): col is DataTableColumn<Model> => Boolean(col));
    // Always keep Actions last if present.
    const withoutActions = visible.filter((col) => col.id !== "actions");
    const actions = byId.get("actions");
    return actions && visibleColumnIds.includes("actions")
      ? [...withoutActions, actions]
      : withoutActions;
  }, [modelColumnTemplates, modelListColumns, visibleColumnIds]);

  const columnPicker = (
    <ModelListColumnPicker
      columns={modelListColumns}
      visibleIds={visibleColumnIds}
      onChange={applyVisibleColumns}
      onReset={resetVisibleColumns}
    />
  );

  return (
    <>
      <Head>
        <title>{`Model Management - ${getPlatformName()}`}</title>
        <meta name="description" content="Manage and configure AI models" />
      </Head>

      <ContentLayout fillHeight>
                <ManagementPageHeader
                    crumbs={false}
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
                      <DataTable
                        layout="admin"
                        fillHeight
                        items={registryItems}
                        columns={modelColumns}
                        sort={modelSort.sort}
                        onSortChange={registry.onSortChange}
                        getRowKey={(model) => model.modelId}
                        onRowClick={(model) => handleViewModel(model.modelId)}
                        paginate="server"
                        paginationPosition="bottom"
                        pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
                        serverPagination={{
                          page: registry.page,
                          pageSize: registry.pageSize,
                          totalItems: registry.total,
                          onPageChange: registry.setPage,
                          onPageSizeChange: registry.onPageSizeChange,
                          pageSizeOptions: DEFAULT_PAGE_SIZE_OPTIONS,
                        }}
                        isLoading={isLoading}
                        loadingMessage="Loading models..."
                        emptyMessage="No models in the registry yet."
                        noResultsMessage="No results found. Try adjusting your search or filters."
                        unfilteredCount={registry.total}
                        hasActiveFilters={registry.hasActiveFilters}
                        onClearFilters={registry.clearFilters}
                        filterToolbarRightContent={columnPicker}
                        search={{
                          label: "Search",
                          value: registry.filters.name ?? "",
                          onChange: (value) => registry.setFilter("name", value),
                          placeholder: "Search by model name...",
                          debounceMs: 400,
                          fields: ["name"],
                        }}
                        filterDefs={[
                          {
                            id: "status",
                            label: "Status",
                            type: "select",
                            param: "version_status",
                            value: registry.filters.status ?? MODEL_VERSION.FILTER.ALL,
                            onChange: (value) => registry.setFilter("status", value),
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
                            param: "task_types",
                            value: toolbarTaskType,
                            onChange: (value) => registry.setFilter("taskType", value),
                            // Fits the longest task type (LANGUAGE-DIARIZATION).
                            width: { base: "full", sm: "240px" },
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
        <FormDrawer
          isOpen={Boolean(isViewingModel && selectedModel)}
          onClose={closeModelView}
          size="wide"
          title={selectedModel?.name || "Model"}
          description="Model configuration."
          actions={
            selectedModel ? (
              <HStack spacing={2}>
                {isRegistryReadOnly ? (
                  <Badge colorScheme="gray" fontSize="xs" px={2} py={0.5}>
                    Read-only
                  </Badge>
                ) : null}
                {!isRegistryReadOnly &&
                  (selectedModel.versionStatus?.toLowerCase() === "active" || !selectedModel.versionStatus) && (
                  <CreateButton
                    size="sm"
                    onClick={() => {
                      const modelId = selectedModel.modelId;
                      const returnTo = `/model-management?modelId=${encodeURIComponent(modelId)}`;
                      router.push(
                        `/services-management?modelId=${encodeURIComponent(modelId)}&tab=create&returnTo=${encodeURIComponent(returnTo)}`,
                      );
                    }}
                  >
                    Create Service
                  </CreateButton>
                )}
                {!isRegistryReadOnly &&
                !isServiceCountLoading &&
                !hasServiceCountError &&
                isModelDeprecated(selectedModel) ? (
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
                ) : !isRegistryReadOnly &&
                  !isServiceCountLoading &&
                  !hasServiceCountError &&
                  isModelActive(selectedModel) &&
                  hasLinkedServices(selectedModel) ? (
                  <Tooltip
                    label={
                      hasPublishedService(selectedModel)
                        ? "Unpublish its services to deprecate"
                        : "Deprecate model"
                    }
                    placement="top"
                    hasArrow
                  >
                    <Box as="span" display="inline-flex" alignItems="center">
                      <Switch
                        size="md"
                        colorScheme="green"
                        isChecked={true}
                        onChange={() => {
                          if (hasPublishedService(selectedModel)) return;
                          openConfirmDialog("deprecate", selectedModel);
                        }}
                        isDisabled={
                          updatingModelId !== null ||
                          hasPublishedService(selectedModel)
                        }
                      />
                    </Box>
                  </Tooltip>
                ) : null}
              </HStack>
            ) : undefined
          }
          footer={<FormActions hideSubmit cancelLabel="Close" onCancel={closeModelView} pt={0} />}
        >
          {selectedModel ? (
            <ModelForm
              mode="view"
              model={selectedModel}
              extra={
                <ModelExtraDetails
                  trainingDataset={selectedModel.trainingDataset}
                  adapterConfig={selectedModel.adapterConfig}
                  schema={selectedModel.schema}
                />
              }
            />
          ) : null}
        </FormDrawer>
        <FormDrawer
          isOpen={isCreateOpen && !isRegistryReadOnly && !(isViewingModel && selectedModel)}
          onClose={closeCreateModal}
          lockDismiss={isUploading}
          size="wide"
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
          {isCreateOpen && !isRegistryReadOnly && !(isViewingModel && selectedModel) ? (
          <ModelForm
            mode="create"
            model={parsedModelData}
            extra={
              parsedModelData ? (
                <ModelExtraDetails
                  trainingDataset={parsedModelData.trainingDataset}
                  adapterConfig={parsedModelData.adapterConfig}
                  schema={parsedModelData.schema}
                />
              ) : null
            }
            fileInputRef={fileInputRef}
            onFileChange={handleFileUpload}
            onDownloadSample={handleDownloadSample}
            isUploading={isUploading}
            isValidating={isValidating}
            validationErrors={validationErrors}
            uploadError={uploadError}
            onClearUpload={handleClearUpload}
            createdModel={uploadedModelData}
            onCopyCreated={() => {
              void copy(
                JSON.stringify(uploadedModelData, null, 2),
                "Model data copied to clipboard",
              );
            }}
          />
          ) : null}
        </FormDrawer>
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
