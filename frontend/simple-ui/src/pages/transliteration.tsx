// Transliteration service testing page

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
} from "@chakra-ui/react";
import Head from "next/head";
import React, { useState } from "react";
import ContentLayout from "../components/common/ContentLayout";
import { performTransliterationInference } from "../services/transliterationService";

const TransliterationPage: React.FC = () => {
  const toast = useToast();
  const [inputText, setInputText] = useState("");
  const [sourceLanguage, setSourceLanguage] = useState("en");
  const [targetLanguage, setTargetLanguage] = useState("hi");
  const [fetching, setFetching] = useState(false);
  const [fetched, setFetched] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [responseTime, setResponseTime] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);

  const handleProcess = async () => {
    if (!inputText.trim()) {
      toast({
        title: "Input Required",
        description: "Please enter text to transliterate.",
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
      const response = await performTransliterationInference(inputText, {
        serviceId: "ai4bharat/indicxlit",
        language: {
          sourceLanguage,
          targetLanguage,
        },
        isSentence: true,
        numSuggestions: 0,
      });
      const endTime = Date.now();
      const calculatedTime = ((endTime - startTime) / 1000).toFixed(2);

      setResult(response.data);
      setResponseTime(parseFloat(calculatedTime));
      setFetched(true);
    } catch (err: any) {
      setError(err.message || "Failed to perform transliteration");
      toast({
        title: "Error",
        description: err.message || "Failed to perform transliteration",
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

  return (
    <>
      <Head>
        <title>Transliteration | AI4Inclusion Console</title>
        <meta
          name="description"
          content="Test Transliteration to convert text between scripts"
        />
      </Head>

      <ContentLayout>
        <Grid
          templateColumns={{ base: "1fr", lg: "1fr 1fr" }}
          gap={8}
          w="full"
          maxW="1400px"
          mx="auto"
        >
          {/* Left Column - Service Details */}
          <GridItem>
            <VStack spacing={6} align="stretch">
              <Heading size="lg" color="gray.800">
                Transliteration Service
              </Heading>
              <Text color="gray.600" fontSize="md">
                Convert text from one script to another while keeping pronunciation intact
              </Text>
            </VStack>
          </GridItem>

          {/* Right Column - Try it out here! */}
          <GridItem>
            <VStack spacing={6} align="stretch">
              <Heading size="md" color="gray.800">
                Try it out here!
              </Heading>

              <HStack spacing={4}>
                <FormControl>
                  <FormLabel fontSize="sm" fontWeight="semibold">
                    Source Language:
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
                    Target Language:
                  </FormLabel>
                  <Select
                    value={targetLanguage}
                    onChange={(e) => setTargetLanguage(e.target.value)}
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
              </HStack>

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
                        {responseTime.toFixed(2)} seconds
                      </Text>
                    </VStack>
                  </HStack>
                </Box>
              )}

              <FormControl>
                <FormLabel fontSize="sm" fontWeight="semibold">
                  Enter text to transliterate:
                </FormLabel>
                <Textarea
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  placeholder="Enter text to transliterate..."
                  rows={6}
                  isDisabled={fetching}
                  bg="white"
                  borderColor="gray.300"
                />
              </FormControl>

              {fetching && (
                <Box>
                  <Text mb={2} fontSize="sm" color="gray.600">
                    Processing text...
                  </Text>
                  <Progress size="xs" isIndeterminate colorScheme="cyan" />
                </Box>
              )}

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

              {fetched && result && result.output && result.output.length > 0 && (
                <Box
                  p={4}
                  bg="blue.50"
                  borderRadius="md"
                  border="1px"
                  borderColor="blue.200"
                >
                  <Text fontSize="sm" fontWeight="semibold" mb={2} color="gray.700">
                    Transliterated Text:
                  </Text>
                  {result.output.map((item: any, index: number) => (
                    <Box key={index}>
                      {item.source && (
                        <Text fontSize="xs" color="gray.600" mb={1}>
                          Source: {item.source}
                        </Text>
                      )}
                      <Text fontSize="md" fontWeight="semibold" color="blue.700">
                        {item.target}
                      </Text>
                    </Box>
                  ))}
                </Box>
              )}

              <Button
                colorScheme="orange"
                onClick={handleProcess}
                isLoading={fetching}
                loadingText="Processing..."
                size="md"
                w="full"
              >
                Transliterate
              </Button>

              {fetched && (
                <Button
                  onClick={clearResults}
                  variant="outline"
                  size="sm"
                  w="full"
                >
                  Clear Results
                </Button>
              )}
            </VStack>
          </GridItem>
        </Grid>
      </ContentLayout>
    </>
  );
};

export default TransliterationPage;
