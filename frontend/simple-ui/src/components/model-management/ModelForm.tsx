import {
  Alert,
  AlertDescription,
  AlertIcon,
  Box,
  Button,
  Center,
  Code,
  FormControl,
  Heading,
  HStack,
  Input,
  Spinner,
  Text,
  VStack,
} from "@chakra-ui/react";
import { CopyIcon } from "@chakra-ui/icons";
import React from "react";
import { FIELD_HINTS } from "../../config/fieldHints";
import FieldHint from "../common/FieldHint";
import FieldLabel from "../common/FieldLabel";
import FormSection from "../common/FormSection";
import ModelReview, { type ModelReviewSource } from "./ModelReview";

type ModelFormProps = {
  mode: "create" | "view";
  model: ModelReviewSource | null;
  /** Training dataset, adapter, and schema. Same block on review and view. */
  extra?: React.ReactNode;
  fileInputRef?: React.RefObject<HTMLInputElement>;
  onFileChange?: (event: React.ChangeEvent<HTMLInputElement>) => void;
  onDownloadSample?: () => void;
  isUploading?: boolean;
  isValidating?: boolean;
  validationErrors?: string[];
  uploadError?: string | null;
  onClearUpload?: () => void;
  createdModel?: unknown;
  onCopyCreated?: () => void;
};

/**
 * Model create is a JSON upload. View and the post-upload review show the
 * same parsed fields. There is no field-by-field edit of the JSON.
 */
export default function ModelForm({
  mode,
  model,
  extra,
  fileInputRef,
  onFileChange,
  onDownloadSample,
  isUploading = false,
  isValidating = false,
  validationErrors = [],
  uploadError = null,
  onClearUpload,
  createdModel,
  onCopyCreated,
}: ModelFormProps) {
  return (
    <VStack spacing={0} align="stretch">
      {mode === "create" ? (
        <FormSection title="Upload Model Definition">
          <FormControl>
            <HStack justify="space-between" mb={2} align="center">
              <FieldLabel formLabelProps={{ mb: 0 }}>Upload JSON File</FieldLabel>
              <Button size="sm" variant="outline" onClick={onDownloadSample}>
                Download Sample JSON
              </Button>
            </HStack>
            <Input
              ref={fileInputRef}
              type="file"
              accept=".json"
              onChange={onFileChange}
              disabled={isUploading || isValidating}
              bg="white"
              p={2}
            />
            <FieldHint mt={2}>{FIELD_HINTS.model.jsonUpload.helper}</FieldHint>
            <Text mt={2} fontSize="xs" color="ink.500" lineHeight="1.5">
              Required (ULCA): name (5–100 chars, no spaces), version, description
              (25–1000 chars), task.type, license (closed enum), domain (closed enum,
              at least one), trainingDataset.description, submitter.name. Optional:
              refUrl, languages (Indic and English codes only), licenseUrl,
              isLangDetectionEnabled, isMultilingual, adapterConfig, schema,
              benchmarks. modelId is generated from name:version. submittedOn and
              updatedOn are server-set unless you override them.
            </Text>
          </FormControl>
        </FormSection>
      ) : null}

      {isValidating ? (
        <Center py={8}>
          <VStack spacing={3}>
            <Spinner size="lg" />
            <Text color="ink.600" fontSize="sm">Validating JSON file...</Text>
          </VStack>
        </Center>
      ) : null}

      {isUploading ? (
        <Center py={8}>
          <VStack spacing={3}>
            <Spinner size="lg" />
            <Text color="ink.600" fontSize="sm">Creating model...</Text>
          </VStack>
        </Center>
      ) : null}

      {validationErrors.length > 0 ? (
        <Alert status="error" borderRadius="md" mt={4}>
          <AlertIcon />
          <AlertDescription>
            <VStack align="stretch" spacing={3}>
              <Box>
                <Text fontWeight="semibold" mb={2}>Validation Failed</Text>
                <Text mb={2}>Please fix the following errors:</Text>
                <Box as="ul" pl={4}>
                  {validationErrors.map((error, index) => (
                    <Text key={index} as="li" fontSize="sm" mb={1}>
                      {error}
                    </Text>
                  ))}
                </Box>
              </Box>
              <Button size="sm" variant="outline" onClick={onClearUpload} alignSelf="flex-start">
                Clear & Upload New File
              </Button>
            </VStack>
          </AlertDescription>
        </Alert>
      ) : null}

      {uploadError && validationErrors.length === 0 ? (
        <Alert status="error" borderRadius="md" mt={4}>
          <AlertIcon />
          <AlertDescription>
            <VStack align="stretch" spacing={3}>
              <Box>
                <Text fontWeight="semibold" mb={2}>Error</Text>
                <Text>{uploadError}</Text>
              </Box>
              <Button size="sm" variant="outline" onClick={onClearUpload} alignSelf="flex-start">
                Clear & Upload New File
              </Button>
            </VStack>
          </AlertDescription>
        </Alert>
      ) : null}

      {mode === "create" && model && !isUploading && !isValidating ? (
        <>
          <Alert status="success" borderRadius="md" mt={4} mb={2}>
            <AlertIcon />
            <AlertDescription>
              JSON file validated successfully. Review the data below and choose Create Model.
            </AlertDescription>
          </Alert>
          <FormSection title="Review Model">
            <VStack align="stretch" spacing={6}>
              <ModelReview model={model} />
              {extra}
            </VStack>
          </FormSection>
        </>
      ) : null}

      {mode === "view" && model ? (
        <FormSection title="Review Model">
          <VStack align="stretch" spacing={6}>
            <ModelReview model={model} showStatus />
            {extra}
          </VStack>
        </FormSection>
      ) : null}

      {createdModel ? (
        <Box mt={4}>
          <Alert status="success" borderRadius="md" mb={4}>
            <AlertIcon />
            <AlertDescription>
              Model created successfully. Copy the data if you need a record. This page stays open until you go back.
            </AlertDescription>
          </Alert>
          <HStack justify="space-between" align="center" mb={3}>
            <Heading size="sm" color="ink.700">Created Model Data</Heading>
            <Button size="sm" variant="outline" leftIcon={<CopyIcon />} onClick={onCopyCreated}>
              Copy
            </Button>
          </HStack>
          <Box bg="ink.50" p={4} borderRadius="md" border="1px solid" borderColor="ink.200">
            <Code display="block" whiteSpace="pre-wrap" fontSize="sm" p={4} bg="white" borderRadius="md">
              {JSON.stringify(createdModel, null, 2)}
            </Code>
          </Box>
          <Button mt={4} variant="outline" onClick={onClearUpload}>
            Upload Another Model
          </Button>
        </Box>
      ) : null}
    </VStack>
  );
}
