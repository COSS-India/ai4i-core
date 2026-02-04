// OCR service testing page

import {
  Box,
  Button,
  FormControl,
  FormLabel,
  Grid,
  GridItem,
  Heading,
  HStack,
  Input,
  Progress,
  Select,
  Text,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
  useToast,
  VStack,
  IconButton,
  Icon,
  Spinner,
} from "@chakra-ui/react";
import Head from "next/head";
import React, { useState, useRef, useEffect } from "react";
import { CopyIcon, CheckIcon, AttachmentIcon, DeleteIcon } from "@chakra-ui/icons";
import { useQuery } from "@tanstack/react-query";
import ContentLayout from "../components/common/ContentLayout";
import { performOCRInference, listOCRServices } from "../services/ocrService";

const OCRPage: React.FC = () => {
  const toast = useToast();
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
    staleTime: 10 * 60 * 1000, // 10 minutes
  });

  // Auto-select first available OCR service when list loads
  useEffect(() => {
    if (!ocrServices || ocrServices.length === 0) return;
    if (!selectedServiceId) {
      // If no service selected, select first available
      setSelectedServiceId(ocrServices[0].service_id);
    }
  }, [ocrServices, selectedServiceId]);

  /**
   * Validates if a URL is safe to use as an image source.
   * Only allows http:, https:, blob:, and data:image/* protocols.
   * Rejects dangerous protocols like javascript: to prevent XSS attacks.
   */
  const isSafeImageUrl = (url: string): boolean => {
    if (!url || url.trim() === "") {
      return false;
    }

    try {
      // Check if it's a blob URL (created by URL.createObjectURL)
      if (url.startsWith("blob:")) {
        return true;
      }

      // Parse the URL to check its protocol
      const parsedUrl = new URL(url);

      // Allow http and https protocols
      if (parsedUrl.protocol === "http:" || parsedUrl.protocol === "https:") {
        return true;
      }

      // Allow data URLs, but only for images
      if (parsedUrl.protocol === "data:") {
        // Check if it's a data URL with image media type
        const dataUrlMatch = url.match(/^data:image\//);
        return dataUrlMatch !== null;
      }

      // Reject all other protocols (including javascript:, etc.)
      return false;
    } catch (error) {
      // If URL parsing fails, it's not a valid URL
      return false;
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      processFile(file);
    }
  };

  const processFile = (file: File) => {
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
    const file = e.dataTransfer.files?.[0];
    if (file && file.type.startsWith('image/')) {
      processFile(file);
    } else {
      toast({
        title: "Invalid File",
        description: "Please upload an image file.",
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
      if (isSafeImageUrl(value)) {
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
      reader.onerror = (error) => reject(error);
    });
  };

  const handleProcess = async () => {
    if (!imageFile && !imageUri) {
      toast({
        title: "Input Required",
        description: "Please upload an image or provide an image URL.",
        status: "warning",
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
        imageContent = await fileToBase64(imageFile);
      } else {
        imageUriValue = imageUri;
      }

      if (!selectedServiceId) {
        toast({
          title: "Service Required",
          description: "Please select an OCR service.",
          status: "warning",
          duration: 3000,
          isClosable: true,
        });
        setFetching(false);
        return;
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
      setResponseTime(parseFloat(calculatedTime));
      setFetched(true);
    } catch (err: any) {
      // Prioritize API error message from response
      let errorMessage = "Failed to perform OCR inference";
      
      if (err?.response?.data?.detail?.message) {
        errorMessage = err.response.data.detail.message;
      } else if (err?.response?.data?.message) {
        errorMessage = err.response.data.message;
      } else if (err?.response?.data?.detail) {
        if (typeof err.response.data.detail === 'string') {
          errorMessage = err.response.data.detail;
        }
      } else if (err?.message) {
        errorMessage = err.message;
      }
      
      setError(errorMessage);
      toast({
        title: "Error",
        description: errorMessage,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
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
    navigator.clipboard.writeText(extractedText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
    toast({
      title: "Copied!",
      description: "Text copied to clipboard",
      status: "success",
      duration: 2000,
      isClosable: true,
    });
  };

  return (
    <>
      <Head>
        <title>OCR - Optical Character Recognition | AI4Inclusion Console</title>
        <meta
          name="description"
          content="Test OCR to extract text from images"
        />
      </Head>

      <ContentLayout>
        <VStack spacing={8} w="full">
          {/* Page Header */}
          <Box textAlign="center">
            <Heading size="xl" color="gray.800" mb={2} userSelect="none" cursor="default" tabIndex={-1}>
              OCR - Optical Character Recognition
            </Heading>
            <Text color="gray.600" fontSize="lg" userSelect="none" cursor="default">
              OCR service for Indic and English languages running on NVIDIA T4 GPU. Provides high-accuracy text extraction from images with bounding boxes, confidence scores, and line-by-line results.
            </Text>
          </Box>

        <Grid
          templateColumns={{ base: "1fr", lg: "1fr 1fr" }}
          gap={8}
          w="full"
            maxW="1200px"
          mx="auto"
        >
            {/* Configuration Panel */}
            <GridItem>
              <VStack spacing={6} align="stretch">
                {/* Service Selection */}
                <FormControl>
                  <FormLabel fontSize="sm" fontWeight="semibold">
                    OCR Service:
                  </FormLabel>
                  {servicesLoading ? (
                    <HStack spacing={2} p={2}>
                      <Spinner size="sm" color="orange.500" />
                      <Text fontSize="sm" color="gray.600">Loading services...</Text>
                    </HStack>
                  ) : (
                    <Select
                      value={selectedServiceId}
                      onChange={(e) => setSelectedServiceId(e.target.value)}
                      placeholder="Select a OCR service"
                      disabled={fetching}
                      size="md"
                      borderColor="gray.300"
                      _focus={{
                        borderColor: "orange.400",
                        boxShadow: "0 0 0 1px var(--chakra-colors-orange-400)",
                      }}
                    >
                      {ocrServices?.map((service) => (
                        <option key={service.service_id} value={service.service_id}>
                          {service.name || service.service_id} {service.model_version ? `(${service.model_version})` : ''}
                        </option>
                      ))}
                    </Select>
                  )}
                  {selectedServiceId && ocrServices && (
                    <Box mt={2} p={3} bg="orange.50" borderRadius="md" border="1px" borderColor="orange.200">
                      {(() => {
                        const selectedService = ocrServices.find(s => s.service_id === selectedServiceId);
                        return selectedService ? (
                          <>
                            <Text fontSize="sm" color="gray.700" mb={1}>
                              <strong>Service ID:</strong> {selectedService.service_id}
                            </Text>
                            <Text fontSize="sm" color="gray.700" mb={1}>
                              <strong>Name:</strong> {selectedService.name || selectedService.service_id}
                            </Text>
                            <Text fontSize="sm" color="gray.700" mb={1}>
                              <strong>Description:</strong> {selectedService.serviceDescription || "No description available"}
                            </Text>
                          </>
                        ) : null;
                      })()}
                    </Box>
                  )}
                </FormControl>

              <FormControl>
                <FormLabel fontSize="sm" fontWeight="semibold">
                  Upload Image for OCR:
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
                        isDisabled={fetching}
                        display="none"
                      />

                      {/* Drag and drop zone */}
                      {!imageFile ? (
                        <Box
                          onDragOver={handleDragOver}
                          onDragLeave={handleDragLeave}
                          onDrop={handleDrop}
                          border="2px dashed"
                          borderColor={isDragging ? "teal.400" : "gray.300"}
                          borderRadius="lg"
                          p={8}
                          textAlign="center"
                          bg={isDragging ? "teal.50" : "gray.50"}
                          cursor="pointer"
                          transition="all 0.2s"
                          _hover={{
                            borderColor: "teal.400",
                            bg: "teal.50",
                          }}
                          onClick={handleFileButtonClick}
                        >
                          <VStack spacing={4}>
                            <Icon as={AttachmentIcon} boxSize={10} color={isDragging ? "teal.500" : "gray.400"} />
                            <VStack spacing={1}>
                              <Text fontSize="md" fontWeight="semibold" color="gray.700">
                                {isDragging ? "Drop image here" : "Click to upload or drag and drop"}
                              </Text>
                              <Text fontSize="sm" color="gray.500">
                                Select an image file from your device
                              </Text>
                            </VStack>
                            <Button
                              size="sm"
                              colorScheme="teal"
                              leftIcon={<AttachmentIcon />}
                              onClick={(e) => {
                                e.stopPropagation();
                                handleFileButtonClick();
                              }}
                            >
                              Choose File
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
                        isDisabled={fetching}
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

              {previewUrl && (
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
                      src={previewUrl}
                      alt="Preview"
                      style={{ maxWidth: "100%", height: "auto", display: "block" }}
                    />
                  </Box>
                </Box>
              )}

                <Button
                  colorScheme="orange"
                  onClick={handleProcess}
                  isLoading={fetching}
                  loadingText="Processing..."
                  size="md"
                  w="full"
                  isDisabled={!imageFile && !imageUri}
                >
                  Extract Text
                </Button>
              </VStack>
            </GridItem>

            {/* Results Panel */}
            <GridItem>
              <VStack spacing={6} align="stretch">
                {/* Progress Indicator */}
              {fetching && (
                <Box>
                  <Text mb={2} fontSize="sm" color="gray.600">
                    Processing image...
                  </Text>
                    <Progress size="xs" isIndeterminate colorScheme="orange" />
                </Box>
              )}

                {/* Error Display */}
              {error && (
                <Box
                  p={4}
                  bg="red.50"
                  borderRadius="md"
                  border="1px"
                  borderColor="red.200"
                >
                  <Text color="red.600" fontSize="sm">
                    {error}
                  </Text>
                </Box>
              )}

                {/* Metrics Box */}
                {fetched && (
                  <Box
                    p={4}
                    bg="orange.50"
                    borderRadius="md"
                    border="1px"
                    borderColor="orange.200"
                  >
                    <HStack spacing={6}>
                      <VStack align="start" spacing={0}>
                        <Text fontSize="xs" color="gray.600">
                          Characters Extracted
                        </Text>
                        <Text fontSize="lg" fontWeight="bold" color="gray.800">
                          {characterCount} characters
                        </Text>
                      </VStack>
                      <VStack align="start" spacing={0}>
                        <Text fontSize="xs" color="gray.600">
                          Response Time
                        </Text>
                        <Text fontSize="lg" fontWeight="bold" color="gray.800">
                          {responseTime.toFixed(2)} seconds
                        </Text>
                      </VStack>
                    </HStack>
                  </Box>
                )}

                {/* OCR Results */}
              {fetched && extractedText && (
                  <>
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

                    {/* Clear Results Button */}
                    <Box textAlign="center">
                      <button
                  onClick={clearResults}
                        style={{
                          padding: "8px 16px",
                          backgroundColor: "#f7fafc",
                          border: "1px solid #e2e8f0",
                          borderRadius: "6px",
                          cursor: "pointer",
                          fontSize: "14px",
                          color: "#4a5568",
                        }}
                >
                  Clear Results
                      </button>
                    </Box>
                  </>
              )}
            </VStack>
          </GridItem>
        </Grid>
        </VStack>
      </ContentLayout>
    </>
  );
};

export default OCRPage;
