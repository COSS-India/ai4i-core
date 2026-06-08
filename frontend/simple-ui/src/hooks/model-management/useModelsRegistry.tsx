import {
  Badge,
  Box,
  HStack,
  IconButton,
  Switch,
  Text,
  Tooltip,
} from "@chakra-ui/react";
import { ViewIcon } from "@chakra-ui/icons";
import { useState, useEffect, useMemo, useCallback } from "react";
import { fetchAllModelsMatchingFilters } from "../../services/modelManagementService";
import { listServices as listServicesForModels } from "../../services/servicesManagementService";
import { extractErrorInfo } from "../../utils/errorHandler";
import { useToastWithDeduplication } from "../useToastWithDeduplication";
import type { AdminTableColumn } from "../../components/common/AdminDataTable";
import {
  formatModelVersionStatusLabel,
  isModelVersionStatusActive,
} from "../../config/constants";
import { getTaskColor } from "../../components/model-management/utils";
import type { ConfirmAction, HandleViewModelRef, Model, OpenConfirmDialogRef } from "./shared";

type UseModelsRegistryParams = {
  handleViewModelRef: HandleViewModelRef;
  openConfirmDialogRef: OpenConfirmDialogRef;
  updatingModelId: string | null;
  isRegistryReadOnly: boolean;
};

export function useModelsRegistry({
  handleViewModelRef,
  openConfirmDialogRef,
  updatingModelId,
  isRegistryReadOnly,
}: UseModelsRegistryParams) {
  const [models, setModels] = useState<Model[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [modelIdsWithPublishedService, setModelIdsWithPublishedService] = useState<Set<string>>(
    new Set()
  );
  const [searchQuery, setSearchQuery] = useState("");
  const [filterVersionStatus, setFilterVersionStatus] = useState<string>("");
  const [filterTaskType, setFilterTaskType] = useState<string>("");
  const [sortBy, setSortBy] = useState<"time" | "name">("time");
  const [nameSortDirection, setNameSortDirection] = useState<"asc" | "desc">("asc");
  const toast = useToastWithDeduplication();

  const fetchModels = useCallback(async () => {
    setIsLoading(true);
    try {
      const result = await fetchAllModelsMatchingFilters({
        taskType: filterTaskType || undefined,
        versionStatus: filterVersionStatus || undefined,
      });
      setModels(result.items as unknown as Model[]);
    } catch (error: unknown) {
      console.error("Failed to fetch models:", error);
      const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(error);
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMessage,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      setModels([]);
    } finally {
      setIsLoading(false);
    }
  }, [filterTaskType, filterVersionStatus, toast]);

  useEffect(() => {
    fetchModels();
  }, [fetchModels]);

  useEffect(() => {
    const fetchServices = async () => {
      try {
        const svcs = await listServicesForModels();
        const ids = new Set<string>();
        (svcs || []).forEach(
          (s: {
            modelId?: string;
            model_id?: string;
            isPublished?: boolean;
            is_published?: boolean;
          }) => {
            const id = s.modelId ?? s.model_id;
            const published = s.isPublished === true || s.is_published === true;
            if (id && published) ids.add(String(id));
          }
        );
        setModelIdsWithPublishedService(ids);
      } catch {
        setModelIdsWithPublishedService(new Set());
      }
    };
    fetchServices();
  }, []);

  const registryTableItems = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const filtered = q ? models.filter((m) => (m.name ?? "").toLowerCase().includes(q)) : models;
    if (sortBy === "time") return filtered;
    return [...filtered].sort((a, b) => {
      const nameCmp = (a.name ?? "").localeCompare(b.name ?? "", undefined, { sensitivity: "base" });
      if (nameCmp !== 0) return nameSortDirection === "asc" ? nameCmp : -nameCmp;
      return 0;
    });
  }, [models, searchQuery, sortBy, nameSortDirection]);

  const hasActiveFilters =
    filterVersionStatus !== "" || filterTaskType !== "" || searchQuery.trim() !== "";

  const clearAllFilters = () => {
    setSearchQuery("");
    setFilterVersionStatus("");
    setFilterTaskType("");
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
          <Badge colorScheme={isModelVersionStatusActive(model.versionStatus) ? "green" : "gray"} fontSize="xs">
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
                onClick={() => handleViewModelRef.current?.(model.modelId)}
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
                      onChange={() =>
                        openConfirmDialogRef.current?.("deprecate" as ConfirmAction, model)
                      }
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
                      onChange={() =>
                        openConfirmDialogRef.current?.("activate" as ConfirmAction, model)
                      }
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

  return {
    models,
    isLoading,
    modelIdsWithPublishedService,
    searchQuery,
    setSearchQuery,
    filterVersionStatus,
    setFilterVersionStatus,
    filterTaskType,
    setFilterTaskType,
    sortBy,
    nameSortDirection,
    registryTableItems,
    hasActiveFilters,
    clearAllFilters,
    fetchModels,
    modelColumns,
  };
}
