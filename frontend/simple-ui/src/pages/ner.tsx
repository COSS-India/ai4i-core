// NER service testing page

import {
  Box,
  Button,
  FormControl,
  FormLabel,
  Grid,
  GridItem,
  Heading,
  HStack,
  Progress,
  Select,
  Text,
  Textarea,
  useToast,
  VStack,
  Badge,
} from "@chakra-ui/react";
import Head from "next/head";
import React, { useState } from "react";
import ContentLayout from "../components/common/ContentLayout";
import { performNERInference } from "../services/nerService";
import { extractErrorInfo } from "../utils/errorHandler";

const NERPage: React.FC = () => {
  const toast = useToast();
  const [inputText, setInputText] = useState("");
  const [sourceLanguage, setSourceLanguage] = useState("en");
  const [fetching, setFetching] = useState(false);
  const [fetched, setFetched] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [responseTime, setResponseTime] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);

  const handleProcess = async () => {
    if (!inputText.trim()) {
      toast({
        title: "Input Required",
        description: "Please enter text to process.",
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
      const startTime = Date.now();
      const response = await performNERInference(inputText, {
        serviceId: "dhruva-ner",
        language: {
          sourceLanguage,
        },
      });
      const endTime = Date.now();
      const calculatedTime = ((endTime - startTime) / 1000).toFixed(3);

      setResult(response.data);
      setResponseTime(parseFloat(calculatedTime));
      setFetched(true);
    } catch (err: any) {
      // Use centralized error handler
      const { title: errorTitle, message: errorMessage } = extractErrorInfo(err);
      
      setError(errorMessage);
      toast({
        title: errorTitle,
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
    setInputText("");
    setError(null);
  };

  const getEntityColor = (label: string) => {
    const colors: { [key: string]: string } = {
      ORG: "orange",
      LOC: "blue",
      PER: "green",
      MISC: "purple",
      O: "gray", // Other/Outside tag
    };
    return colors[label] || "gray";
  };

  return (
    <>
      <Head>
        <title>NER - Named Entity Recognition | AI4Inclusion Console</title>
        <meta
          name="description"
          content="Test Named Entity Recognition to identify entities in text"
        />
      </Head>

      <ContentLayout>
        <VStack spacing={8} w="full">
          {/* Page Header */}
          <Box textAlign="center">
            <Heading size="xl" color="gray.800" mb={2}>
              Named Entity Recognition (NER)
            </Heading>
            <Text color="gray.600" fontSize="lg">
              Identify key entities like names, locations, and organizations in text
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

              <FormControl>
                <FormLabel fontSize="sm" fontWeight="semibold">
                  Select Language:
                </FormLabel>
                <Select
                  value={sourceLanguage}
                  onChange={(e) => setSourceLanguage(e.target.value)}
                  isDisabled={fetching}
                  size="md"
                >
                  <option value="en">English</option>
                  <option value="hi">Hindi</option>
                  <option value="ta">Tamil</option>
                  <option value="te">Telugu</option>
                  <option value="kn">Kannada</option>
                  <option value="ml">Malayalam</option>
                  <option value="mr">Marathi</option>
                  <option value="gu">Gujarati</option>
                  <option value="bn">Bengali</option>
                  <option value="pa">Punjabi</option>
                  <option value="or">Odia</option>
                  <option value="as">Assamese</option>
                </Select>
              </FormControl>

              <FormControl>
                <FormLabel fontSize="sm" fontWeight="semibold">
                  Enter text to identify entities:
                </FormLabel>
                <Textarea
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  placeholder="Enter text to identify entities..."
                  rows={6}
                  isDisabled={fetching}
                  bg="white"
                  borderColor="gray.300"
                />
              </FormControl>

                <Button
                  colorScheme="orange"
                  onClick={handleProcess}
                  isLoading={fetching}
                  loadingText="Processing..."
                  size="md"
                  w="full"
                >
                  {fetching ? "Processing..." : "Detect Entities"}
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
                    Processing text...
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
                          Response Time
                        </Text>
                        <Text fontSize="lg" fontWeight="bold" color="gray.800">
                          {responseTime.toFixed(3)} seconds
                        </Text>
                      </VStack>
                    </HStack>
                  </Box>
                )}

                {/* NER Results */}
              {fetched && result && result.output && result.output.length > 0 && (
                  <>
                <Box
                  p={4}
                  bg="gray.50"
                  borderRadius="md"
                  border="1px"
                  borderColor="gray.200"
                >
                  <Text fontSize="sm" fontWeight="semibold" mb={3} color="gray.700">
                    Identified Entities:
                  </Text>
                  <VStack align="stretch" spacing={2}>
                    {(() => {
                      // Handle both response formats:
                      // 1. New format: nerPrediction array with token/tag
                      // 2. Old format: entities array with text/label
                      const firstOutput = result.output[0];
                      let entities: any[] = [];
                      
                      if (firstOutput?.nerPrediction) {
                        // Transform nerPrediction to entities format
                        entities = firstOutput.nerPrediction
                          .filter((pred: any) => pred.tag) // Only filter out entries without tags
                          .map((pred: any) => ({
                            text: pred.token,
                            label: pred.tag,
                            start: pred.tokenStartIndex || 0,
                            end: pred.tokenEndIndex || 0,
                          }));
                      } else if (firstOutput?.entities) {
                        entities = firstOutput.entities;
                      }
                      
                      if (entities.length === 0) {
                        return (
                          <Text fontSize="sm" color="gray.500" fontStyle="italic">
                            No entities found in the text.
                          </Text>
                        );
                      }
                      
                      return entities.map((entity: any, index: number) => (
                        <HStack key={index} spacing={2}>
                          <Badge
                            colorScheme={getEntityColor(entity.label)}
                            fontSize="xs"
                            px={2}
                            py={1}
                            borderRadius="full"
                          >
                            {entity.label}
                          </Badge>
                          <Text fontSize="sm" color="gray.700">
                            {entity.text}
                          </Text>
                        </HStack>
                      ));
                    })()}
                  </VStack>
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

export default NERPage;
