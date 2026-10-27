import {
  Alert,
  AlertDescription,
  AlertIcon,
  Box,
  Button,
  Center,
  Code,
  Collapse,
  FormControl,
  Heading,
  HStack,
  Input,
  Link,
  SimpleGrid,
  Spinner,
  Text,
  useDisclosure,
  VStack,
} from "@chakra-ui/react";
import { CopyIcon } from "@chakra-ui/icons";
import React, { useEffect, useState } from "react";
import { FiArrowUpRight, FiChevronDown, FiDownload, FiInfo } from "react-icons/fi";
import { FIELD_HINTS } from "../../config/fieldHints";
import { getModelSpecUrls } from "../../config/runtimeConfig";
import type { ModelSampleKind } from "../../utils/sampleModelJson";
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
  onDownloadSample?: (kind: ModelSampleKind) => void;
  isUploading?: boolean;
  isValidating?: boolean;
  validationErrors?: string[];
  uploadError?: string | null;
  onClearUpload?: () => void;
  createdModel?: unknown;
  onCopyCreated?: () => void;
};

type ModelJsonUploadProps = Pick<ModelFormProps, "fileInputRef" | "onDownloadSample"> & {
  fileName: string;
  isBusy: boolean;
  onFileChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
};

/** Create-mode upload: per-kind spec cards (spec link + sample), JSON file picker, and field requirements. */
function ModelJsonUpload({
  fileName,
  isBusy,
  fileInputRef,
  onFileChange,
  onDownloadSample,
}: ModelJsonUploadProps) {
  const specUrls = getModelSpecUrls();
  const requirements = useDisclosure();

  return (
    <FormSection title="Upload Model Definition">
      {/* isExternal opens a new tab so the admin keeps what's already in the drawer. */}
      <SimpleGrid mb={5} columns={2} spacing={3}>
        {FIELD_HINTS.model.jsonUpload.specReferences.map((spec) => (
          <Box
            key={spec.id}
            title={spec.text}
            p={3}
            borderWidth="1px"
            borderColor="blue.100"
            borderRadius="md"
            bg="blue.50"
          >
            <HStack mb={2} justify="space-between" align="center" flexWrap="wrap" spacing={2}>
              <Text
                as="span"
                px={2}
                py="1px"
                fontSize="xs"
                fontWeight="600"
                color="ink.700"
                bg="ink.200"
                borderRadius="md"
              >
                {spec.badge}
              </Text>
              <Button
                size="xs"
                variant="outline"
                bg="white"
                leftIcon={<FiDownload aria-hidden />}
                onClick={() => onDownloadSample?.(spec.sampleKind)}
                aria-label={spec.sampleLabel}
              >
                Sample JSON
              </Button>
            </HStack>
            <Link
              href={specUrls[spec.id]}
              isExternal
              display="flex"
              alignItems="center"
              gap={1}
              fontSize="sm"
              fontWeight="600"
              color="blue.600"
              aria-label={`${spec.linkLabel} (opens in a new tab)`}
            >
              {spec.shortLabel}
              <FiArrowUpRight aria-hidden />
            </Link>
          </Box>
        ))}
      </SimpleGrid>
      <FormControl>
        <FieldLabel formLabelProps={{ mb: 2, htmlFor: "model-json-file" }}>
          Upload JSON File
        </FieldLabel>
        <Box
          position="relative"
          h="40px"
          borderWidth="1px"
          borderColor="ink.200"
          borderRadius="md"
          bg="white"
          opacity={isBusy ? 0.6 : 1}
          _focusWithin={{
            borderColor: "blue.500",
            boxShadow: "0 0 0 1px var(--chakra-colors-blue-500)",
          }}
        >
          <Input
            id="model-json-file"
            ref={fileInputRef}
            type="file"
            accept=".json"
            onChange={onFileChange}
            disabled={isBusy}
            position="absolute"
            top={0}
            left={0}
            w="full"
            h="full"
            opacity={0}
            p={0}
            m={0}
            cursor={isBusy ? "not-allowed" : "pointer"}
            zIndex={1}
            sx={{ "&::file-selector-button": { display: "none" } }}
          />
          <HStack h="full" px={2} spacing={3} pointerEvents="none">
            <Text
              as="span"
              px={3}
              h="28px"
              display="inline-flex"
              alignItems="center"
              flexShrink={0}
              borderWidth="1px"
              borderColor="ink.200"
              borderRadius="md"
              bg="ink.50"
              fontSize="sm"
              fontWeight="600"
              color="ink.800"
            >
              Browse
            </Text>
            <Text fontSize="sm" color={fileName ? "ink.800" : "ink.500"} noOfLines={1}>
              {fileName || "Select a .json file"}
            </Text>
          </HStack>
        </Box>
        <FieldHint mt={2}>{FIELD_HINTS.model.jsonUpload.helper}</FieldHint>
        <Box mt={4} bg="ink.50" borderRadius="md">
          <Button
            variant="unstyled"
            display="flex"
            alignItems="center"
            w="full"
            h="auto"
            px={3}
            py={2.5}
            fontSize="sm"
            fontWeight="500"
            color="ink.600"
            onClick={requirements.onToggle}
            aria-expanded={requirements.isOpen}
            aria-controls="model-field-requirements"
          >
            <Box as={FiInfo} aria-hidden mr={2} />
            Field requirements
            <Box
              as={FiChevronDown}
              aria-hidden
              ml="auto"
              transform={requirements.isOpen ? "rotate(180deg)" : undefined}
              transition="transform 0.2s"
            />
          </Button>
          <Collapse in={requirements.isOpen} animateOpacity>
            <VStack
              id="model-field-requirements"
              align="stretch"
              spacing={3}
              px={3}
              pb={3}
              fontSize="xs"
              color="ink.500"
              lineHeight="1.5"
            >
              <Text>{FIELD_HINTS.model.jsonUpload.requirements.required}</Text>
              <VStack align="stretch" spacing={1}>
                {FIELD_HINTS.model.jsonUpload.requirements.byKind.map((item) => (
                  <Text key={item.label}>
                    <Text as="span" fontWeight="600" color="ink.700">
                      {item.label}:
                    </Text>{" "}
                    {item.text}
                  </Text>
                ))}
              </VStack>
            </VStack>
          </Collapse>
        </Box>
      </FormControl>
    </FormSection>
  );
}

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
  const [fileName, setFileName] = useState("");
  const isBusy = isUploading || isValidating;

  useEffect(() => {
    if (createdModel) setFileName("");
  }, [createdModel]);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setFileName(event.target.files?.[0]?.name ?? "");
    onFileChange?.(event);
  };

  const handleClear = () => {
    setFileName("");
    onClearUpload?.();
  };

  return (
    <VStack spacing={0} align="stretch">
      {mode === "create" ? (
        <ModelJsonUpload
          fileName={fileName}
          isBusy={isBusy}
          fileInputRef={fileInputRef}
          onFileChange={handleFileChange}
          onDownloadSample={onDownloadSample}
        />
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
              <Button size="sm" variant="outline" onClick={handleClear} alignSelf="flex-start">
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
              <Button size="sm" variant="outline" onClick={handleClear} alignSelf="flex-start">
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
          <Button mt={4} variant="outline" onClick={handleClear}>
            Upload Another Model
          </Button>
        </Box>
      ) : null}
    </VStack>
  );
}
