import { useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { mapToServiceOptions } from "../components/service-page";
import { OCR_ERRORS } from "../config/constants";
import { performOCRInference, listOCRServices } from "../services/ocrService";
import type { OCRInferenceResponse } from "../types/inference";
import type { InferenceModelMetadata } from "../types/feedback";
import { parseError } from "../utils/errorHandler";
import { parseOCRResponse } from "../utils/ocrResponseUtils";
import {
  prepareOCRImagePayload,
  requireOCRService,
  showOCRError,
  updateImageUriPreview,
  validateOCRImageFile,
} from "../utils/ocrPageUtils";
import { sanitizeImagePreviewUrl } from "../utils/safeImageUrl";
import { showToast } from "../utils/toast";

export function useOCRPage() {
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imageUri, setImageUri] = useState("");
  const [sourceLanguage] = useState("en");
  const [selectedServiceId, setSelectedServiceId] = useState("");
  const [fetching, setFetching] = useState(false);
  const [fetched, setFetched] = useState(false);
  const [result, setResult] = useState<OCRInferenceResponse | null>(null);
  const [responseTime, setResponseTime] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [lastRequestId, setLastRequestId] = useState<string | null>(null);
  const [lastModelMeta, setLastModelMeta] = useState<InferenceModelMetadata | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: ocrServices, isLoading: servicesLoading } = useQuery({
    queryKey: ["ocr-services"],
    queryFn: listOCRServices,
    staleTime: 10 * 60 * 1000,
  });

  const serviceOptions = useMemo(
    () => mapToServiceOptions(ocrServices ?? []),
    [ocrServices]
  );

  const canExtract =
    !!selectedServiceId.trim() &&
    (!!imageFile || !!imageUri.trim()) &&
    !fetching;

  const blockMediaInput = fetching || !selectedServiceId.trim();
  const safePreviewUrl = useMemo(
    () => sanitizeImagePreviewUrl(previewUrl),
    [previewUrl]
  );

  const ocrParseResult = useMemo(
    () => (result ? parseOCRResponse(result.output?.[0]?.source) : null),
    [result]
  );
  const extractedText = ocrParseResult?.ok ? ocrParseResult.text : "";
  const ocrParseError =
    fetched && ocrParseResult && !ocrParseResult.ok ? ocrParseResult.error : null;

  const processFile = (file: File) => {
    if (!requireOCRService(selectedServiceId)) return;
    const validationError = validateOCRImageFile(file);
    if (validationError) {
      showOCRError(validationError);
      return;
    }
    setImageFile(file);
    setImageUri("");
    setPreviewUrl(URL.createObjectURL(file));
    setActiveTab(0);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) processFile(file);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (!requireOCRService(selectedServiceId)) return;
    const file = e.dataTransfer.files?.[0];
    if (file?.type.startsWith("image/")) {
      processFile(file);
      return;
    }
    showOCRError(OCR_ERRORS.INVALID_FORMAT);
  };

  const handleFileButtonClick = () => fileInputRef.current?.click();

  const handleRemoveFile = () => {
    setImageFile(null);
    setPreviewUrl(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleUriChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setImageUri(value);
    setImageFile(null);
    setActiveTab(1);
    setPreviewUrl(updateImageUriPreview(value));
  };

  const handleProcess = async () => {
    if (!selectedServiceId.trim()) {
      showToast({ type: "warning", message: "Please select an OCR service before extracting text." });
      return;
    }
    if (!imageFile && !imageUri.trim()) {
      showOCRError(OCR_ERRORS.FILE_REQUIRED);
      return;
    }

    setFetching(true);
    setError(null);
    setFetched(false);

    try {
      const payload = await prepareOCRImagePayload(imageFile, imageUri);
      if (!payload.ok) return;

      const startTime = Date.now();
      const response = await performOCRInference(
        payload.imageContent,
        payload.imageUri,
        {
          serviceId: selectedServiceId,
          language: { sourceLanguage, sourceScriptCode: "" },
          textDetection: true,
        }
      );

      setResult(response.data);
      setResponseTime((Date.now() - startTime) / 1000);
      setLastRequestId(response.requestId ?? null);
      setLastModelMeta(response.model ?? response.data.model ?? null);
      setFetched(true);
    } catch (err: unknown) {
      setError(parseError(err, { service: "ocr" }).message);
    } finally {
      setFetching(false);
    }
  };

  const clearResults = () => {
    setFetched(false);
    setResult(null);
    setImageFile(null);
    setImageUri("");
    setPreviewUrl(null);
    setError(null);
    setLastRequestId(null);
    setLastModelMeta(null);
  };

  return {
    imageFile,
    imageUri,
    selectedServiceId,
    setSelectedServiceId,
    fetching,
    fetched,
    error: error || ocrParseError,
    extractedText,
    responseTime,
    lastRequestId,
    lastModelMeta,
    ocrServices,
    activeTab,
    setActiveTab,
    isDragging,
    blockMediaInput,
    canExtract,
    safePreviewUrl,
    serviceOptions,
    servicesLoading,
    fileInputRef,
    handleFileChange,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    handleFileButtonClick,
    handleRemoveFile,
    handleUriChange,
    handleProcess,
    clearResults,
  };
}
