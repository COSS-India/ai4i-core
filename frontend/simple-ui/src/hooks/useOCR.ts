// Custom hook for OCR image text extraction

import { useCallback, useEffect, useMemo, useState } from "react";
import { useToastWithDeduplication } from "./useToastWithDeduplication";
import { performOCRInference } from "../services/ocrService";
import { OCR_ERRORS } from "../config/constants";
import { extractErrorInfo } from "../utils/errorHandler";
import { isSafeImageUrl } from "../components/service-page/utils";
import { parseOcrSource } from "../components/service-page/utils/parseOcrResult";
import type { OCRInferenceResponse } from "../types/inference";

const fileToBase64 = (file: File): Promise<string> => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => {
      const base64 = (reader.result as string).split(",")[1];
      resolve(base64);
    };
    reader.onerror = (error) => reject(error);
  });
};

const isValidOcrImage = (file: File): boolean => {
  const isJPG =
    file.type === "image/jpeg" ||
    file.type === "image/jpg" ||
    file.name.toLowerCase().endsWith(".jpg") ||
    file.name.toLowerCase().endsWith(".jpeg");
  const isPNG = file.type === "image/png" || file.name.toLowerCase().endsWith(".png");
  return isJPG || isPNG;
};

export const validateOcrImageFile = (file: File): string | null => {
  if (!isValidOcrImage(file)) {
    return OCR_ERRORS.INVALID_FORMAT.description;
  }
  return null;
};

export const useOCR = () => {
  const toast = useToastWithDeduplication();
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imageUri, setImageUri] = useState("");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [sourceLanguage] = useState("en");
  const [selectedServiceId, setSelectedServiceId] = useState("");
  const [fetching, setFetching] = useState(false);
  const [fetched, setFetched] = useState(false);
  const [result, setResult] = useState<OCRInferenceResponse | null>(null);
  const [responseTime, setResponseTime] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (imageFile) {
      const url = URL.createObjectURL(imageFile);
      setPreviewUrl(url);
      return () => URL.revokeObjectURL(url);
    }
    if (imageUri?.trim() && isSafeImageUrl(imageUri)) {
      setPreviewUrl(imageUri);
      return;
    }
    setPreviewUrl(null);
  }, [imageFile, imageUri]);

  const handleFileChange = useCallback(
    (file: File | null) => {
      if (file && !selectedServiceId?.trim()) {
        toast({
          title: "Service Required",
          description: "Please select an OCR service before uploading an image.",
          status: "warning",
          duration: 3000,
          isClosable: true,
        });
        return;
      }
      setImageFile(file);
      if (file) setImageUri("");
    },
    [selectedServiceId, toast]
  );

  const handleImageUrlChange = useCallback(
    (url: string) => {
      if (url && !selectedServiceId?.trim()) {
        toast({
          title: "Service Required",
          description: "Please select an OCR service before providing an image URL.",
          status: "warning",
          duration: 3000,
          isClosable: true,
        });
        return;
      }
      setImageUri(url);
      if (url) setImageFile(null);
    },
    [selectedServiceId, toast]
  );

  const parsedResult = useMemo(
    () => parseOcrSource(result?.output?.[0]?.source ?? ""),
    [result]
  );
  const extractedText = parsedResult.plainText;

  const performExtraction = useCallback(async () => {
    if (!selectedServiceId?.trim()) {
      toast({
        title: "Service Required",
        description: "Please select an OCR service before extracting text.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    if (!imageFile && !imageUri?.trim()) {
      const err = OCR_ERRORS.FILE_REQUIRED;
      toast({
        title: err.title,
        description: err.description,
        status: "error",
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    setFetching(true);
    setError(null);
    setFetched(false);

    try {
      let imageContent: string | null = null;
      let imageUriValue: string | null = null;

      if (imageFile) {
        try {
          imageContent = await fileToBase64(imageFile);
          if (!imageContent || imageContent.length === 0) {
            throw new Error("EMPTY_FILE");
          }
        } catch (err: unknown) {
          const ocrErr =
            err instanceof Error && err.message === "EMPTY_FILE"
              ? OCR_ERRORS.EMPTY_FILE
              : OCR_ERRORS.INVALID_FILE;
          toast({
            title: ocrErr.title,
            description: ocrErr.description,
            status: "error",
            duration: 3000,
            isClosable: true,
          });
          setFetching(false);
          return;
        }
      } else {
        imageUriValue = imageUri;
      }

      const startTime = Date.now();
      const response = await performOCRInference(imageContent, imageUriValue, {
        serviceId: selectedServiceId,
        language: {
          sourceLanguage,
          sourceScriptCode: "",
        },
        textDetection: true,
      });
      const endTime = Date.now();

      setResult(response.data);
      setResponseTime((endTime - startTime) / 1000);
      setFetched(true);
    } catch (err: unknown) {
      const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(err, "ocr");
      setError(errorMessage);
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMessage,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setFetching(false);
    }
  }, [imageFile, imageUri, selectedServiceId, sourceLanguage, toast]);

  const clearResults = useCallback(() => {
    setFetched(false);
    setResult(null);
    setImageFile(null);
    setImageUri("");
    setError(null);
  }, []);

  const canExtract =
    !!selectedServiceId?.trim() &&
    (!!imageFile || !!imageUri?.trim()) &&
    !fetching;

  return {
    imageFile,
    imageUri,
    previewUrl,
    selectedServiceId,
    fetching,
    fetched,
    result,
    parsedResult,
    extractedText,
    responseTime,
    error,
    canExtract,
    setSelectedServiceId,
    handleFileChange,
    handleImageUrlChange,
    performExtraction,
    clearResults,
  };
};
