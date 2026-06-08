// OCR service testing page — reusable service page architecture

import { useQuery } from "@tanstack/react-query";
import React, { useMemo } from "react";
import {
  buildResponseMetadata,
  mapToServiceOptions,
  RequestContainer,
  ResponseContainer,
  ServicePageLayout,
  useCopyToClipboard,
} from "../components/service-page";
import OcrResult from "../components/service-page/results/OcrResult";
import { getServicePageDefaults } from "../config/servicePageConfig";
import { useOCR, validateOcrImageFile } from "../hooks/useOCR";
import { listOCRServices } from "../services/ocrService";

const pageDefaults = getServicePageDefaults("ocr");

const OCRPage: React.FC = () => {
  const { copy } = useCopyToClipboard();
  const {
    imageFile,
    imageUri,
    previewUrl,
    selectedServiceId,
    fetching,
    fetched,
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
  } = useOCR();

  const { data: ocrServices, isLoading: servicesLoading } = useQuery({
    queryKey: ["ocr-services"],
    queryFn: listOCRServices,
    staleTime: 10 * 60 * 1000,
  });

  const serviceOptions = useMemo(
    () => mapToServiceOptions(ocrServices ?? []),
    [ocrServices]
  );

  const metadata = buildResponseMetadata({
    responseTimeMs: responseTime * 1000,
  });

  return (
    <ServicePageLayout
      serviceId="ocr"
      headTitle="OCR - Optical Character Recognition | AI4Inclusion Console"
      headDescription="Test OCR to extract text from images"
      requestPanel={
        <RequestContainer
          inputType="image"
          serviceDropdown={{
            label: "OCR Service",
            value: selectedServiceId,
            onChange: setSelectedServiceId,
            options: serviceOptions,
            loading: servicesLoading,
            disabled: fetching,
          }}
          imageInput={{
            file: imageFile,
            onFileChange: handleFileChange,
            previewUrl,
            imageUrl: imageUri,
            onImageUrlChange: handleImageUrlChange,
            showUrlTab: true,
            label: "Upload Image for OCR",
            disabled: fetching || !selectedServiceId?.trim(),
            acceptedFormats: ".jpg,.jpeg,.png,image/jpeg,image/png",
            formatHint: "Supported formats: PNG, JPG, JPEG (Max size: 10MB)",
            validateFile: validateOcrImageFile,
          }}
          helperText={pageDefaults.helperText}
          submitButton={{
            label: pageDefaults.submitLabel,
            loadingLabel: pageDefaults.submitLoadingLabel,
            onClick: performExtraction,
            isLoading: fetching,
            isDisabled: !canExtract,
          }}
        />
      }
      responsePanel={
        <ResponseContainer
          fetching={fetching}
          fetchingLabel="Processing image..."
          error={error}
          fetched={fetched}
          hasResult={!!extractedText}
          result={fetched && extractedText ? <OcrResult parsed={parsedResult} /> : undefined}
          metadata={
            fetched && extractedText
              ? [...metadata, { label: "Characters extracted", value: extractedText.length }]
              : []
          }
          actions={
            fetched && extractedText
              ? [
                  {
                    id: "copy",
                    label: "Copy",
                    kind: "copy",
                    onClick: () => copy(extractedText, "Text copied to clipboard."),
                  },
                ]
              : []
          }
          onClear={clearResults}
        />
      }
    />
  );
};

export default OCRPage;
