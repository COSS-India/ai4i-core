import { useState, useEffect } from "react";
import { createService, type Service } from "../../services/servicesManagementService";
import { getAllModels, getModelById } from "../../services/modelManagementService";
import type { ModelDetails } from "../../types/platform";
import { extractErrorInfo } from "../../utils/errorHandler";
import { useToastWithDeduplication } from "../useToastWithDeduplication";
import {
  formatModelSubmissionDate,
  invalidateServiceRegistryQueries,
} from "../../components/services-management/utils";
import type { FetchServicesRef, PreselectedModelState, RegistryPageContext } from "./shared";
import { initialCreateFormState } from "./shared";

type UseServiceCreateParams = RegistryPageContext & {
  fetchServicesRef: FetchServicesRef;
  setRegistryEpoch: React.Dispatch<React.SetStateAction<number>>;
  setActiveTab: React.Dispatch<React.SetStateAction<number>>;
};

export function useServiceCreate({
  router,
  queryClient,
  isRegistryReadOnly,
  checkSessionExpiry,
  fetchServicesRef,
  setRegistryEpoch,
  setActiveTab,
}: UseServiceCreateParams) {
  const toast = useToastWithDeduplication();
  const [models, setModels] = useState<ModelDetails[]>([]);
  const [isLoadingModels, setIsLoadingModels] = useState(false);
  const [formData, setFormData] = useState<Partial<Service>>(initialCreateFormState);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [preselectedModelFromQuery, setPreselectedModelFromQuery] =
    useState<ModelDetails | null>(null);

  const preselectedNotDeprecated =
    preselectedModelFromQuery &&
    preselectedModelFromQuery.versionStatus?.toLowerCase() !== "deprecated";
  const modelsForDropdown =
    preselectedNotDeprecated &&
    !models.some(
      (m) =>
        (m.modelId || m.model_id) ===
        (preselectedModelFromQuery.modelId || preselectedModelFromQuery.model_id)
    )
      ? [preselectedModelFromQuery, ...models]
      : models;

  useEffect(() => {
    const fetchModels = async () => {
      setIsLoadingModels(true);
      try {
        const fetchedModels = await getAllModels();
        const activeModels = fetchedModels.filter(
          (model) => model.versionStatus?.toLowerCase() === "active" || !model.versionStatus
        );
        setModels(activeModels);
      } catch (error: unknown) {
        console.error("Failed to fetch models:", error);
        setModels([]);
      } finally {
        setIsLoadingModels(false);
      }
    };

    fetchModels();
  }, []);

  const handleInputChange = (field: keyof Service, value: string) => {
    setFormData((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  const handleModelNameChange = async (modelId: string) => {
    if (!checkSessionExpiry()) return;
    if (modelId) {
      try {
        setIsLoadingModels(true);
        const modelDetails = await getModelById(modelId);

        const taskType =
          modelDetails?.task?.type || modelDetails?.task_type || modelDetails?.taskType || "";
        const modelVersion = modelDetails?.version || modelDetails?.modelVersion || "1.0";
        const modelSubmissionDate = formatModelSubmissionDate(
          modelDetails?.submittedOn ?? modelDetails?.submitted_on ?? ""
        );
        const modelName = modelDetails?.name || modelDetails?.modelId || modelDetails?.model_id || "";

        setFormData((prev) => ({
          ...prev,
          modelId: modelId,
          modelName: modelName,
          task_type: taskType,
          modelSubmissionDate: modelSubmissionDate,
          modelVersion: modelVersion,
        }));
      } catch (error: unknown) {
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
      setFormData((prev) => ({
        ...prev,
        modelId: "",
        modelName: "",
        task_type: "",
        modelSubmissionDate: "",
        modelVersion: "",
      }));
    }
  };

  useEffect(() => {
    if (isRegistryReadOnly) return;
    const { modelId, tab } = router.query;
    if (!modelId || typeof modelId !== "string") return;

    const runPreselect = async () => {
      if (tab === "create") {
        setActiveTab(1);
      }

      const inActiveList = models.some((m) => (m.modelId || m.model_id) === modelId);
      if (inActiveList && formData.modelId !== modelId) {
        handleModelNameChange(modelId);
        const { tab: currentTab } = router.query;
        const nextQuery: Record<string, string> = {};
        if (typeof currentTab === "string") {
          nextQuery.tab = currentTab;
        }
        router.replace(
          { pathname: "/services-management", query: nextQuery },
          undefined,
          { shallow: true }
        );
        return;
      }

      if (!inActiveList) {
        try {
          const modelDetails = await getModelById(modelId);
          const isDeprecated = modelDetails?.versionStatus?.toLowerCase() === "deprecated";
          if (modelDetails && !isDeprecated) {
            setPreselectedModelFromQuery(modelDetails);
            if (formData.modelId !== modelId) {
              handleModelNameChange(modelId);
            }
          }
        } catch (e) {
          console.error("Failed to load preselected model:", e);
        }
        const { tab: currentTab } = router.query;
        const nextQuery: Record<string, string> = {};
        if (typeof currentTab === "string") {
          nextQuery.tab = currentTab;
        }
        router.replace(
          { pathname: "/services-management", query: nextQuery },
          undefined,
          { shallow: true }
        );
      }
    };

    if (models.length > 0) {
      runPreselect();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router.query, models]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!checkSessionExpiry()) return;

    setIsSubmitting(true);

    try {
      const timestamp = Date.now();
      const serviceId = `${formData.name?.toLowerCase().replace(/\s+/g, "-") || "service"}-${timestamp}`;

      const serviceFormData: Partial<Service> = { ...formData };
      delete serviceFormData.modelSubmissionDate;
      const serviceData: Partial<Service> = {
        ...serviceFormData,
        serviceId: serviceId,
        publishedOn: Math.floor(Date.now() / 1000),
        hardwareDescription: "Default hardware",
        api_key: "",
        status: "active",
      };

      await createService(serviceData);

      invalidateServiceRegistryQueries(queryClient);

      toast({
        title: "Service created",
        description: "Service has been created successfully.",
        status: "success",
        duration: 5000,
        isClosable: true,
      });

      setFormData(initialCreateFormState());
      setPreselectedModelFromQuery(null);

      await fetchServicesRef.current?.();
      setRegistryEpoch((e) => e + 1);

      setActiveTab(0);
    } catch (error: unknown) {
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

  const canCreateService =
    !!formData.name?.trim() &&
    !!formData.serviceDescription?.trim() &&
    !!formData.modelId?.trim() &&
    !!formData.endpoint?.trim();

  const isCreateFormModelSelected = !!formData.modelId?.trim();

  const resetCreateForm = () => {
    setFormData(initialCreateFormState());
    setPreselectedModelFromQuery(null);
  };

  return {
    models,
    isLoadingModels,
    formData,
    isSubmitting,
    preselectedModelFromQuery,
    setPreselectedModelFromQuery,
    modelsForDropdown,
    handleInputChange,
    handleModelNameChange,
    handleSubmit,
    canCreateService,
    isCreateFormModelSelected,
    resetCreateForm,
  };
}

export type { PreselectedModelState };
