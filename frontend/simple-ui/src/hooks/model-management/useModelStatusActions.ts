import { useDisclosure } from "@chakra-ui/react";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { getModelById, updateModel } from "../../services/modelManagementService";
import { MODEL_VERSION } from "../../config/constants";
import { extractErrorInfo } from "../../utils/errorHandler";
import { useToastWithDeduplication } from "../useToastWithDeduplication";
import type {
  ConfirmAction,
  FetchModelsRef,
  Model,
  OpenConfirmDialogRef,
  RegistryPageContext,
} from "./shared";

type UseModelStatusActionsParams = RegistryPageContext & {
  fetchModelsRef: FetchModelsRef;
  openConfirmDialogRef: OpenConfirmDialogRef;
  selectedModel: Model | null;
  setSelectedModel: React.Dispatch<React.SetStateAction<Model | null>>;
  setUpdateFormData: React.Dispatch<React.SetStateAction<Partial<Model>>>;
};

export function useModelStatusActions({
  checkSessionExpiry,
  fetchModelsRef,
  openConfirmDialogRef,
  selectedModel,
  setSelectedModel,
  setUpdateFormData,
}: UseModelStatusActionsParams) {
  const toast = useToastWithDeduplication();
  const [updatingModelId, setUpdatingModelId] = useState<string | null>(null);
  const [modelToConfirm, setModelToConfirm] = useState<Model | null>(null);
  const [confirmAction, setConfirmAction] = useState<ConfirmAction | null>(null);
  const { isOpen: isConfirmOpen, onOpen: onConfirmOpen, onClose: onConfirmClose } = useDisclosure();
  const cancelConfirmRef = useRef<HTMLButtonElement>(null);

  const handleDeprecateModel = async (model: Model) => {
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
        versionStatus: MODEL_VERSION.STATUS.DEPRECATED,
      });

      toast({
        title: "Model deprecated",
        description: `${model.name || model.modelId} has been deprecated successfully.`,
        status: "success",
        duration: 5000,
        isClosable: true,
      });

      await fetchModelsRef.current?.();
      if (selectedModel && selectedModel.modelId === model.modelId) {
        const updatedModel = await getModelById(model.modelId);
        setSelectedModel(updatedModel as unknown as Model);
        setUpdateFormData(updatedModel as unknown as Partial<Model>);
      }
    } catch (error: unknown) {
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
        versionStatus: MODEL_VERSION.STATUS.ACTIVE,
      });

      toast({
        title: "Model activated",
        description: `${model.name || model.modelId} has been activated successfully.`,
        status: "success",
        duration: 5000,
        isClosable: true,
      });

      await fetchModelsRef.current?.();
      if (selectedModel && selectedModel.modelId === model.modelId) {
        const updatedModel = await getModelById(model.modelId);
        setSelectedModel(updatedModel as unknown as Model);
        setUpdateFormData(updatedModel as unknown as Partial<Model>);
      }
    } catch (error: unknown) {
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

  const openConfirmDialog = useCallback(
    (action: ConfirmAction, model: Model) => {
      setModelToConfirm(model);
      setConfirmAction(action);
      onConfirmOpen();
    },
    [onConfirmOpen]
  );

  useEffect(() => {
    openConfirmDialogRef.current = openConfirmDialog;
  }, [openConfirmDialog, openConfirmDialogRef]);

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

  return {
    updatingModelId,
    modelToConfirm,
    confirmAction,
    isConfirmOpen,
    cancelConfirmRef,
    openConfirmDialog,
    handleConfirmAction,
    closeConfirmDialog,
  };
}
