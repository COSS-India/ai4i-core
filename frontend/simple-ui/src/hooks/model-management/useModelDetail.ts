import { useState, useEffect, useCallback } from "react";
import { getModelById, updateModel } from "../../services/modelManagementService";
import { useToastWithDeduplication } from "../useToastWithDeduplication";
import type {
  FetchModelsRef,
  HandleViewModelRef,
  Model,
  RegistryPageContext,
} from "./shared";

type UseModelDetailParams = RegistryPageContext & {
  fetchModelsRef: FetchModelsRef;
  handleViewModelRef: HandleViewModelRef;
  setActiveTab: React.Dispatch<React.SetStateAction<number>>;
};

export function useModelDetail({
  router,
  viewTabIndex,
  checkSessionExpiry,
  fetchModelsRef,
  handleViewModelRef,
  setActiveTab,
}: UseModelDetailParams) {
  const toast = useToastWithDeduplication();
  const [selectedModel, setSelectedModel] = useState<Model | null>(null);
  const [isViewingModel, setIsViewingModel] = useState(false);
  const [isEditingModel, setIsEditingModel] = useState(false);
  const [updateFormData, setUpdateFormData] = useState<Partial<Model>>({});
  const [isUpdating, setIsUpdating] = useState(false);

  const handleViewModel = useCallback(
    async (modelId: string) => {
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
        router.replace(
          { pathname: "/model-management", query: { ...router.query, tab: "2" } },
          undefined,
          { shallow: true }
        );
      } catch (error) {
        toast({
          title: "Failed to Load Model",
          description: error instanceof Error ? error.message : "Failed to fetch model details",
          status: "error",
          duration: 5000,
          isClosable: true,
        });
      }
    },
    [checkSessionExpiry, router, setActiveTab, toast, viewTabIndex]
  );

  useEffect(() => {
    handleViewModelRef.current = handleViewModel;
  }, [handleViewModel, handleViewModelRef]);

  const handleUpdateModel = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedModel) return;

    if (!checkSessionExpiry()) return;

    setIsUpdating(true);
    try {
      const updateData = {
        modelId: selectedModel.modelId,
        name: updateFormData.name,
        description: updateFormData.description,
        task: updateFormData.task,
        license: updateFormData.license,
        source: updateFormData.source,
        domain: updateFormData.domain || [],
        languages: updateFormData.languages || [],
      };

      await updateModel(updateData as Parameters<typeof updateModel>[0]);

      toast({
        title: "Model Updated",
        description: "Model has been updated successfully",
        status: "success",
        duration: 3000,
        isClosable: true,
      });

      await fetchModelsRef.current?.();
      const updatedModel = await getModelById(selectedModel.modelId);
      setSelectedModel(updatedModel as unknown as Model);
      setUpdateFormData(updatedModel as unknown as Partial<Model>);
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

  return {
    selectedModel,
    setSelectedModel,
    isViewingModel,
    setIsViewingModel,
    isEditingModel,
    updateFormData,
    setUpdateFormData,
    isUpdating,
    handleViewModel,
    handleUpdateModel,
  };
}
