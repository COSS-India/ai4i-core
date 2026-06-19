// OCR service testing page

import {
  Box,
  Button,
  FormControl,
  FormLabel,
  HStack,
  Input,
  Select,
  Text,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
  VStack,
  IconButton,
  Icon,
} from "@chakra-ui/react";
import React, { useState, useRef, useEffect, useMemo } from "react";
import { CopyIcon, CheckIcon, AttachmentIcon, DeleteIcon } from "@chakra-ui/icons";
import { FaUpload } from "react-icons/fa";
import { useQuery } from "@tanstack/react-query";
import {
  buildResponseMetadata,
  mapToServiceOptions,
  RequestContainer,
  ResponseContainer,
  ServicePageLayout,
  useCopyToClipboard,
} from "../components/service-page";
import { getServicePageDefaults } from "../config/servicePageConfig";
import { performOCRInference, listOCRServices } from "../services/ocrService";
import { OCR_ERRORS, MAX_IMAGE_FILE_SIZE } from "../config/constants";
import { parseError } from "../utils/errorHandler";
import {
  isSafeUserImageUrl,
  sanitizeImagePreviewUrl,
} from "../utils/safeImageUrl";
import { useToastWithDeduplication } from "../utils/toast";

const pageDefaults = getServicePageDefaults("ocr");

const OCRPage: React.FC = () => {
  const toast = useToastWithDeduplication();
  const { copy } = useCopyToClipboard();
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imageUri, setImageUri] = useState("");
  const [sourceLanguage, setSourceLanguage] = useState("en");
  const [selectedServiceId, setSelectedServiceId] = useState("");
  const [fetching, setFetching] = useState(false);
  const [fetched, setFetched] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [responseTime, setResponseTime] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch available OCR services
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
    !!selectedServiceId?.trim() &&
    (!!imageFile || !!imageUri?.trim()) &&
    !fetching;

  const blockMediaInput = fetching || !selectedServiceId?.trim();

  const safePreviewUrl = useMemo(
    () => sanitizeImagePreviewUrl(previewUrl),
    [previewUrl]
  );

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      processFile(file);
    }
  };

  const processFile = (file: File) => {
    if (!selectedServiceId?.trim()) {
      toast({
        title: "Service Required",
        description: "Please select an OCR service before uploading an image.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    // Validate file type
    const isJPG = file.type === 'image/jpeg' || file.type === 'image/jpg' || file.name.toLowerCase().endsWith('.jpg') || file.name.toLowerCase().endsWith('.jpeg');
    const isPNG = file.type === 'image/png' || file.name.toLowerCase().endsWith('.png');

    if (!isJPG && !isPNG) {
      const err = OCR_ERRORS.INVALID_FORMAT;
      toast({
        title: err.title,
        description: err.description,
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    // Validate file size
    if (file.size > MAX_IMAGE_FILE_SIZE) {
      const err = OCR_ERRORS.FILE_TOO_LARGE;
      toast({
        title: err.title,
        description: err.description,
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    // Validate file is not empty
    if (file.size === 0) {
      const err = OCR_ERRORS.EMPTY_FILE;
      toast({
        title: err.title,
        description: err.description,
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    setImageFile(file);
    setImageUri("");
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    setActiveTab(0);
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
    if (!selectedServiceId?.trim()) {
      toast({
        title: "Service Required",
        description: "Please select an OCR service before uploading an image.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    const file = e.dataTransfer.files?.[0];
    if (file && file.type.startsWith('image/')) {
      processFile(file);
    } else {
      const err = OCR_ERRORS.INVALID_FORMAT;
      toast({
        title: err.title,
        description: err.description,
        status: "error",
        duration: 3000,
        isClosable: true,
      });
    }
  };

  const handleFileButtonClick = () => {
    fileInputRef.current?.click();
  };

  const handleRemoveFile = () => {
    setImageFile(null);
    setPreviewUrl(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

   const handleUriChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setImageUri(value);
    setImageFile(null);
    setActiveTab(1);

    // Validate URL before setting preview
    if (value && value.trim() !== "") {
      if (isSafeUserImageUrl(value)) {
        setPreviewUrl(value);
      } else {
        // Clear preview and show error for unsafe URLs
        setPreviewUrl(null);
        toast({
          title: "Invalid URL",
          description: "Please provide a valid image URL (http://, https://, or data:image/*).",
          status: "error",
          duration: 3000,
          isClosable: true,
        });
      }
    } else {
      setPreviewUrl(null);
    }
  };

  const fileToBase64 = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = () => {
        const base64 = (reader.result as string).split(",")[1];
        resolve(base64);
      };
      reader.onerror = () => reject(new Error('File read failed'));
    });
  };

  const handleProcess = async () => {
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
            throw new Error('EMPTY_FILE');
          }
        } catch (err: any) {
          const error = err?.message === 'EMPTY_FILE'
            ? OCR_ERRORS.EMPTY_FILE
            : OCR_ERRORS.INVALID_FILE;
          toast({
            title: error.title,
            description: error.description,
            status: 'error',
            duration: 3000,
            isClosable: true,
          });
          setFetching(false);
          return;
        }
      } else if (!isSafeUserImageUrl(imageUri)) {
        toast({
          title: "Invalid URL",
          description:
            "Please provide a valid image URL (http://, https://, or data:image/*).",
          status: "error",
          duration: 3000,
          isClosable: true,
        });
        setFetching(false);
        return;
      } else {
        imageUriValue = imageUri;
      }

      const startTime = Date.now();
      const response = await performOCRInference(
        imageContent,
        imageUriValue,
        {
          serviceId: selectedServiceId,
          language: {
            sourceLanguage,
            sourceScriptCode: "",
          },
          textDetection: true,
        }
      );
      const endTime = Date.now();
      const calculatedTime = ((endTime - startTime) / 1000).toFixed(2);

      setResult(response.data);
      setResponseTime(Number.parseFloat(calculatedTime));
      setFetched(true);
    } catch (err: any) {
      // Use centralized error handler (ocr context so backend message shown as default when no specific mapping)
      const { message: errorMessage } = parseError(err, { service: 'ocr' });

      setError(errorMessage);
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
  };

  const extractedText = result?.output?.[0]?.source || "";
  const characterCount = extractedText.length;

  const handleCopy = () => {
    copy(extractedText, "Text copied to clipboard");
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <ServicePageLayout
      serviceId="ocr"
      headTitle="OCR - Optical Character Recognition | AI4Inclusion Console"
      headDescription="Test OCR to extract text from images"
      requestPanel={
        <RequestContainer
          serviceDropdown={{
            label: "OCR Service",
            value: selectedServiceId,
            onChange: setSelectedServiceId,
            options: serviceOptions,
            loading: servicesLoading,
            disabled: fetching,
          }}
          inputType="custom"
          customInput={
            <>
              <FormControl>
                <FormLabel fontSize="sm" fontWeight="semibold">
                  Upload Image for OCR{" "}
                  <Text as="span" color="red.500">*</Text>
                </FormLabel>


                <Tabs index={activeTab} onChange={setActiveTab} mb={4}>
                  <TabList>
                    <Tab fontSize="sm">Upload File</Tab>
                    <Tab fontSize="sm">Image URL</Tab>
                  </TabList>
                  <TabPanels>
                    <TabPanel px={0}>
                      <Text fontSize="xs" color="gray.500" mb={3}>
                        Supported formats: PNG, JPG, JPEG, WebP (Max size: 10MB)
                      </Text>

                      {/* Hidden file input */}
                      <Input
                        ref={fileInputRef}
                        type="file"
                        accept="image/*"
                        onChange={handleFileChange}
                        isDisabled={blockMediaInput}
                        display="none"
                      />

                      {/* Drag and drop zone */}
                      {!imageFile ? (
                        <Box
                          onDragOver={blockMediaInput ? undefined : handleDragOver}
                          onDragLeave={blockMediaInput ? undefined : handleDragLeave}
                          onDrop={blockMediaInput ? undefined : handleDrop}
                          border="2px dashed"
                          borderColor={isDragging ? "teal.400" : "gray.300"}
                          borderRadius="lg"
                          p={8}
                          textAlign="center"
                          bg={isDragging ? "teal.50" : "gray.50"}
                          cursor={blockMediaInput ? "not-allowed" : "pointer"}
                          opacity={blockMediaInput ? 0.6 : 1}
                          transition="all 0.2s"
                          _hover={
                            blockMediaInput
                              ? {}
                              : {
                                  borderColor: "teal.400",
                                  bg: "teal.50",
                                }
                          }
                          onClick={blockMediaInput ? undefined : handleFileButtonClick}
                        >
                          <VStack spacing={4}>
                            <Icon as={AttachmentIcon} boxSize={10} color={isDragging ? "teal.500" : "gray.400"} />
                            <VStack spacing={1}>
                              <Text fontSize="md" fontWeight="semibold" color="gray.700">
                                {isDragging ? "Drop image here" : "Click to upload or drag and drop"}
                              </Text>
                            </VStack>
                            <Button
                              size="sm"
                              colorScheme="teal"
                              leftIcon={<FaUpload />}
                              isDisabled={blockMediaInput}
                              onClick={(e) => {
                                e.stopPropagation();
                                handleFileButtonClick();
                              }}
                            >
                              Upload Image
                            </Button>
                          </VStack>
                        </Box>
                      ) : (
                        <Box
                          border="2px solid"
                          borderColor="green.300"
                          borderRadius="lg"
                          p={4}
                          bg="green.50"
                        >
                          <HStack justify="space-between" align="center">
                            <HStack spacing={3} flex={1}>
                              <Icon as={AttachmentIcon} boxSize={6} color="green.600" />
                              <VStack align="start" spacing={0} flex={1} minW={0}>
                                <Text fontSize="sm" fontWeight="semibold" color="green.800" isTruncated>
                                  {imageFile.name}
                                </Text>
                                <Text fontSize="xs" color="green.600">
                                  {(imageFile.size / 1024 / 1024).toFixed(2)} MB
                                </Text>
                              </VStack>
                            </HStack>
                            <IconButton
                              aria-label="Remove file"
                              icon={<DeleteIcon />}
                              size="sm"
                              variant="ghost"
                              colorScheme="red"
                              onClick={handleRemoveFile}
                            />
                          </HStack>
                        </Box>
                      )}
                    </TabPanel>
                    <TabPanel px={0}>
                      <Input
                        type="url"
                        value={imageUri}
                        onChange={handleUriChange}
                        placeholder="https://example.com/image.jpg"
                        isDisabled={blockMediaInput}
                        size="md"
                        borderColor="gray.300"
                        _focus={{
                          borderColor: "teal.400",
                          boxShadow: "0 0 0 1px var(--chakra-colors-teal-400)",
                        }}
                      />
                    </TabPanel>
                  </TabPanels>
                </Tabs>
              </FormControl>

              {safePreviewUrl && (
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
                      src={safePreviewUrl}
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
            onClick: handleProcess,
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
          metadata={
            fetched
              ? [
                  ...buildResponseMetadata({ responseTimeMs: responseTime * 1000 }),
                  { label: "Characters extracted", value: characterCount },
                ]
              : []
          }
          result={
            fetched && extractedText ? (
              <Box>
                <HStack justify="space-between" mb={2}>
                  <Text fontSize="sm" fontWeight="semibold">
                    Extracted Text:
                  </Text>
                  <IconButton
                    aria-label="Copy text"
                    icon={copied ? <CheckIcon /> : <CopyIcon />}
                    size="sm"
                    onClick={handleCopy}
                    colorScheme={copied ? "green" : "gray"}
                  />
                </HStack>
                <Box
                  p={4}
                  bg="white"
                  borderRadius="md"
                  border="1px"
                  borderColor="gray.300"
                  maxH="300px"
                  overflowY="auto"
                >
                  <Text fontSize="sm" whiteSpace="pre-wrap" wordBreak="break-word">
                    {extractedText}
                  </Text>
                </Box>
              </Box>
            ) : undefined
          }
          onClear={clearResults}
        />
      }
    />
  );
};

export default OCRPage;
