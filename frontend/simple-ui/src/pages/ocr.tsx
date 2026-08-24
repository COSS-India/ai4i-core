// OCR service testing page

import { Box, Text } from "@chakra-ui/react";
import React from "react";
import {
  buildResponseMetadata,
  RequestContainer,
  ResponseContainer,
  ServicePageLayout,
  useCopyToClipboard,
} from "../components/service-page";
import OCRImageUploadInput from "../components/service-page/inputs/OCRImageUploadInput";
import { getServicePageDefaults } from "../config/servicePageConfig";
import { useOCRPage } from "../hooks/useOCRPage";
import { getPlatformName } from "../config/runtimeConfig";

const pageDefaults = getServicePageDefaults("ocr");

const OCRPage: React.FC = () => {
  const { copy } = useCopyToClipboard();
  const ocr = useOCRPage();

  return (
    <ServicePageLayout
      serviceId="ocr"
      headTitle={`OCR - Optical Character Recognition | ${getPlatformName()}`}
      headDescription="Test OCR to extract text from images"
      requestPanel={
        <RequestContainer
          serviceDropdown={{
            label: "OCR Service",
            value: ocr.selectedServiceId,
            onChange: ocr.setSelectedServiceId,
            options: ocr.serviceOptions,
            loading: ocr.servicesLoading,
            disabled: ocr.fetching,
          }}
          inputType="custom"
          customInput={
            <>
              <OCRImageUploadInput
                imageFile={ocr.imageFile}
                imageUri={ocr.imageUri}
                activeTab={ocr.activeTab}
                isDragging={ocr.isDragging}
                blockMediaInput={ocr.blockMediaInput}
                fileInputRef={ocr.fileInputRef}
                onTabChange={ocr.setActiveTab}
                onFileChange={ocr.handleFileChange}
                onDragOver={ocr.handleDragOver}
                onDragLeave={ocr.handleDragLeave}
                onDrop={ocr.handleDrop}
                onFileButtonClick={ocr.handleFileButtonClick}
                onRemoveFile={ocr.handleRemoveFile}
                onUriChange={ocr.handleUriChange}
              />
              {ocr.safePreviewUrl && (
                <Box>
                  <Text fontSize="sm" fontWeight="semibold" mb={2}>
                    Image Preview:
                  </Text>
                  <Box
                    border="1px"
                    borderColor="gray.300"
                    borderRadius="md"
                    overflow="hidden"
                    bg="gray.50"
                    p={2}
                  >
                    <img
                      src={ocr.safePreviewUrl}
                      alt="Preview"
                      style={{ maxWidth: "100%", height: "auto", display: "block" }}
                    />
                  </Box>
                </Box>
              )}
            </>
          }
          helperText={pageDefaults.helperText}
          submitButton={{
            label: pageDefaults.submitLabel,
            loadingLabel: pageDefaults.submitLoadingLabel,
            onClick: ocr.handleProcess,
            isLoading: ocr.fetching,
            isDisabled: !ocr.canExtract,
          }}
        />
      }
      responsePanel={
        <ResponseContainer
          fetching={ocr.fetching}
          fetchingLabel="Processing image..."
          error={ocr.error}
          fetched={ocr.fetched}
          hasResult={!!ocr.extractedText}
          resultTitle="Extracted Text"
          resultContent={ocr.extractedText}
          metadata={
            ocr.fetched && ocr.extractedText
              ? buildResponseMetadata({ responseTimeMs: ocr.responseTime * 1000 })
              : []
          }
          actions={
            ocr.fetched && ocr.extractedText
              ? [
                  {
                    id: "copy",
                    label: "Copy",
                    kind: "copy",
                    onClick: () => copy(ocr.extractedText, "OCR text copied to clipboard."),
                  },
                ]
              : []
          }
          onClear={ocr.clearResults}
        />
      }
    />
  );
};

export default OCRPage;
