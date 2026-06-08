import {
  Alert,
  AlertDescription,
  AlertIcon,
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Code,
  Center,
  FormControl,
  FormLabel,
  Heading,
  HStack,
  Input,
  Spinner,
  Text,
  VStack,
} from "@chakra-ui/react";
import React from "react";
import type { UseModelManagementReturn } from "../../hooks/useModelManagement";

export function ModelCreateForm(props: UseModelManagementReturn) {
  const {
    cardBg,
    cardBorder,
    fileInputRef,
    handleDownloadSample,
    handleFileUpload,
    isUploading,
    isValidating,
    validationErrors,
    uploadError,
    handleClearUpload,
    parsedModelData,
    handleCreateModel,
    uploadedModelData,
  } = props;

  return (
    <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
      <CardHeader>
        <Heading size="md" color="gray.700" userSelect="none" cursor="default">
          Register New Model
        </Heading>
      </CardHeader>
      <CardBody>
        <VStack spacing={6} align="stretch">
          {/* File Upload Section */}
          <Box>
            <FormControl>
              <HStack justify="space-between" mb={2}>
                <FormLabel fontWeight="semibold" mb={0}>
                  Upload JSON File
                </FormLabel>
                <Button size="sm" colorScheme="blue" variant="outline" onClick={handleDownloadSample}>
                  📥 Download Sample JSON
                </Button>
              </HStack>
              <Input
                ref={fileInputRef}
                type="file"
                accept=".json"
                onChange={handleFileUpload}
                disabled={isUploading || isValidating}
                bg="white"
                p={2}
              />
              <Text fontSize="sm" color="gray.500" mt={2}>
                Upload a JSON file containing the model data. The file will be validated before you can create the
                model.
              </Text>
              <Box mt={2} p={3} bg="blue.50" borderRadius="md" border="1px solid" borderColor="blue.200">
                <Text fontSize="xs" fontWeight="semibold" color="blue.700" mb={1}>
                  Required Fields:
                </Text>
                <Text fontSize="xs" color="blue.600">
                  name, version, description, task (with type), languages, license, domain, inferenceEndPoint,
                  submitter. Optional: refUrl, benchmarks. modelId is auto-generated from name and version. Timestamps
                  (submittedOn, updatedOn) will be auto-added if not present.
                </Text>
              </Box>
            </FormControl>
          </Box>

          {/* Validating State */}
          {isValidating && (
            <Center py={8}>
              <VStack spacing={4}>
                <Spinner size="lg" color="blue.500" />
                <Text color="gray.600">Validating JSON file...</Text>
              </VStack>
            </Center>
          )}

          {/* Loading State */}
          {isUploading && (
            <Center py={8}>
              <VStack spacing={4}>
                <Spinner size="lg" color="blue.500" />
                <Text color="gray.600">Creating model...</Text>
              </VStack>
            </Center>
          )}

          {/* Validation Errors Display */}
          {validationErrors.length > 0 && (
            <Alert status="error" borderRadius="md">
              <AlertIcon />
              <AlertDescription>
                <VStack align="stretch" spacing={3}>
                  <Box>
                    <Text fontWeight="semibold" mb={2}>
                      Validation Failed
                    </Text>
                    <Text mb={2}>Please fix the following errors:</Text>
                    <Box as="ul" pl={4}>
                      {validationErrors.map((error, index) => (
                        <Text key={index} as="li" fontSize="sm" mb={1}>
                          {error}
                        </Text>
                      ))}
                    </Box>
                  </Box>
                  <Button
                    size="sm"
                    colorScheme="gray"
                    variant="outline"
                    onClick={handleClearUpload}
                    alignSelf="flex-start"
                  >
                    Clear & Upload New File
                  </Button>
                </VStack>
              </AlertDescription>
            </Alert>
          )}

          {/* General Error Display */}
          {uploadError && validationErrors.length === 0 && (
            <Alert status="error" borderRadius="md">
              <AlertIcon />
              <AlertDescription>
                <VStack align="stretch" spacing={3}>
                  <Box>
                    <Text fontWeight="semibold" mb={2}>
                      Error
                    </Text>
                    <Text>{uploadError}</Text>
                  </Box>
                  <Button
                    size="sm"
                    colorScheme="gray"
                    variant="outline"
                    onClick={handleClearUpload}
                    alignSelf="flex-start"
                  >
                    Clear & Upload New File
                  </Button>
                </VStack>
              </AlertDescription>
            </Alert>
          )}

          {/* Parsed Data - Ready for Creation */}
          {parsedModelData && !isUploading && !isValidating && (
            <Box>
              <Alert status="success" borderRadius="md" mb={4}>
                <AlertIcon />
                <AlertDescription>
                  JSON file validated successfully! Review the data below and click &quot;Register Model&quot; to
                  proceed.
                </AlertDescription>
              </Alert>
              <Box>
                <Heading size="sm" color="gray.700" mb={4} userSelect="none" cursor="default">
                  Parsed Model Data
                </Heading>
                <Box
                  bg="gray.50"
                  p={4}
                  borderRadius="md"
                  border="1px solid"
                  borderColor="gray.200"
                  maxH="600px"
                  overflowY="auto"
                >
                  <Code
                    display="block"
                    whiteSpace="pre-wrap"
                    fontSize="sm"
                    p={4}
                    bg="white"
                    borderRadius="md"
                  >
                    {JSON.stringify(parsedModelData, null, 2)}
                  </Code>
                </Box>
                <HStack spacing={3} mt={4}>
                  <Button
                    colorScheme="green"
                    onClick={handleCreateModel}
                    isLoading={isUploading}
                    loadingText="Creating..."
                  >
                    Register Model
                  </Button>
                  <Button colorScheme="gray" variant="outline" onClick={handleClearUpload}>
                    Cancel
                  </Button>
                </HStack>
              </Box>
            </Box>
          )}

          {/* Success - Model Created */}
          {uploadedModelData && !isUploading && (
            <Box>
              <Alert status="success" borderRadius="md" mb={4}>
                <AlertIcon />
                <AlertDescription>Model created successfully! Model data is displayed below.</AlertDescription>
              </Alert>
              <Box>
                <Heading size="sm" color="gray.700" mb={4} userSelect="none" cursor="default">
                  Created Model Data
                </Heading>
                <Box
                  bg="gray.50"
                  p={4}
                  borderRadius="md"
                  border="1px solid"
                  borderColor="gray.200"
                  maxH="600px"
                  overflowY="auto"
                >
                  <Code
                    display="block"
                    whiteSpace="pre-wrap"
                    fontSize="sm"
                    p={4}
                    bg="white"
                    borderRadius="md"
                  >
                    {JSON.stringify(uploadedModelData, null, 2)}
                  </Code>
                </Box>
                <Button mt={4} colorScheme="blue" onClick={handleClearUpload}>
                  Upload Another Model
                </Button>
              </Box>
            </Box>
          )}
        </VStack>
      </CardBody>
    </Card>
  );
}
