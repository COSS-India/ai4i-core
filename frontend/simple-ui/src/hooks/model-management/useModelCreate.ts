import { useRef, useState } from "react";
import { createModel } from "../../services/modelManagementService";
import { extractErrorInfo } from "../../utils/errorHandler";
import { useToastWithDeduplication } from "../useToastWithDeduplication";
import { downloadSampleModelJson, validateModelData } from "../../components/model-management/utils";
import type { FetchModelsRef, RegistryPageContext } from "./shared";

type UseModelCreateParams = RegistryPageContext & {
  fetchModelsRef: FetchModelsRef;
};

export function useModelCreate({ checkSessionExpiry, fetchModelsRef }: UseModelCreateParams) {
  const toast = useToastWithDeduplication();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadedModelData, setUploadedModelData] = useState<Record<string, unknown> | null>(null);
  const [parsedModelData, setParsedModelData] = useState<Record<string, unknown> | null>(null);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const handleClearUpload = () => {
    setUploadedModelData(null);
    setParsedModelData(null);
    setValidationErrors([]);
    setUploadError(null);
    setIsUploading(false);
    setIsValidating(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleDownloadSample = () => {
    downloadSampleModelJson();
  };

  const handleCreateModel = async () => {
    if (!parsedModelData) return;

    if (!checkSessionExpiry()) return;

    setIsUploading(true);
    setUploadError(null);

    try {
      const currentTimestamp = Math.floor(Date.now() / 1000);
      const { modelId: _ignoredModelId, ...rest } = parsedModelData;
      const modelData = {
        ...rest,
        submittedOn: parsedModelData.submittedOn || currentTimestamp,
        updatedOn: parsedModelData.updatedOn || currentTimestamp,
      };

      const createdModel = await createModel(modelData as Parameters<typeof createModel>[0]);

      setUploadedModelData(createdModel as unknown as Record<string, unknown>);
      setParsedModelData(null);

      toast({
        title: "Model Created",
        description: "Model has been created successfully from JSON file",
        status: "success",
        duration: 3000,
        isClosable: true,
      });

      await fetchModelsRef.current?.();

      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } catch (error: unknown) {
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

    setUploadedModelData(null);
    setParsedModelData(null);
    setValidationErrors([]);
    setUploadError(null);
    setIsValidating(true);

    try {
      if (!file.name.endsWith(".json")) {
        throw new Error("Please upload a JSON file");
      }

      const fileContent = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (e) => {
          resolve(e.target?.result as string);
        };
        reader.onerror = () => {
          reject(new Error("Failed to read file"));
        };
        reader.readAsText(file);
      });

      let parsedData: Record<string, unknown>;
      try {
        parsedData = JSON.parse(fileContent);
      } catch {
        throw new Error("Invalid JSON format. Please check your file.");
      }

      if (typeof parsedData !== "object" || parsedData === null || Array.isArray(parsedData)) {
        throw new Error("JSON must be an object");
      }

      const errors = validateModelData(parsedData);
      if (errors.length > 0) {
        setValidationErrors(errors);
        setUploadError(errors.join("; "));
        setIsValidating(false);
        return;
      }

      setParsedModelData(parsedData);
      setValidationErrors([]);
      setUploadError(null);

      toast({
        title: "File Validated",
        description:
          "JSON file has been validated successfully. Review the data below and click 'Register Model' to proceed.",
        status: "success",
        duration: 3000,
        isClosable: true,
      });
    } catch (error: unknown) {
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

  return {
    uploadedModelData,
    parsedModelData,
    validationErrors,
    isUploading,
    isValidating,
    uploadError,
    fileInputRef,
    handleClearUpload,
    handleDownloadSample,
    handleCreateModel,
    handleFileUpload,
  };
}
