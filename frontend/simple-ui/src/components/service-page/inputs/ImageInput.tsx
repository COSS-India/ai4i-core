// Image upload input for OCR and vision service pages

import React, { useCallback, useRef, useState } from "react";
import {
  Box,
  Button,
  FormControl,
  FormLabel,
  HStack,
  Icon,
  IconButton,
  Input,
  Text,
  VStack,
} from "@chakra-ui/react";
import { AttachmentIcon, DeleteIcon } from "@chakra-ui/icons";
import { FaUpload } from "react-icons/fa";
import { MAX_IMAGE_FILE_SIZE } from "../../../config/constants";
import type { ServiceImageInputProps } from "../../../types/servicePage";
import { showToast } from "../../../utils/toast";

const ImageInput: React.FC<ServiceImageInputProps> = ({
  file,
  onFileChange,
  previewUrl,
  label = "Upload Image",
  required = true,
  disabled = false,
  maxSizeBytes = MAX_IMAGE_FILE_SIZE,
  acceptedFormats = "image/*",
  formatHint = "Supported formats: PNG, JPG, JPEG, WebP (Max size: 10MB)",
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const validateAndSet = useCallback(
    (next: File | null) => {
      if (!next) {
        onFileChange(null);
        return;
      }
      if (!next.type.startsWith("image/")) {
        showToast({ type: "error", message: "Please select an image file." });
        return;
      }
      if (next.size > maxSizeBytes) {
        showToast({
          type: "error",
          message: `Maximum size is ${(maxSizeBytes / 1024 / 1024).toFixed(0)}MB.`,
        });
        return;
      }
      onFileChange(next);
    },
    [maxSizeBytes, onFileChange]
  );

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0] ?? null;
    validateAndSet(selected);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (disabled) return;
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) validateAndSet(dropped);
  };

  return (
    <FormControl>
      <FormLabel fontSize="sm" fontWeight="semibold">
        {label}{" "}
        {required && (
          <Text as="span" color="red.500">
            *
          </Text>
        )}
      </FormLabel>
      <Text fontSize="xs" color="gray.500" mb={3}>
        {formatHint}
      </Text>

      <Input
        ref={fileInputRef}
        type="file"
        accept={acceptedFormats}
        onChange={handleFileChange}
        isDisabled={disabled}
        display="none"
      />

      {!file ? (
        <Box
          onDragOver={
            disabled
              ? undefined
              : (e) => {
                  e.preventDefault();
                  setIsDragging(true);
                }
          }
          onDragLeave={disabled ? undefined : () => setIsDragging(false)}
          onDrop={disabled ? undefined : handleDrop}
          border="2px dashed"
          borderColor={isDragging ? "orange.400" : "gray.300"}
          borderRadius="lg"
          p={8}
          textAlign="center"
          bg={isDragging ? "orange.50" : "gray.50"}
          cursor={disabled ? "not-allowed" : "pointer"}
          opacity={disabled ? 0.6 : 1}
          transition="all 0.2s"
          _hover={
            disabled
              ? {}
              : {
                  borderColor: "orange.400",
                  bg: "orange.50",
                }
          }
          onClick={disabled ? undefined : () => fileInputRef.current?.click()}
        >
          <VStack spacing={4}>
            <Icon as={AttachmentIcon} boxSize={10} color={isDragging ? "orange.500" : "gray.400"} />
            <Text fontSize="md" fontWeight="semibold" color="gray.700">
              {isDragging ? "Drop image here" : "Click to upload or drag and drop"}
            </Text>
            <Button
              size="sm"
              colorScheme="orange"
              leftIcon={<FaUpload />}
              isDisabled={disabled}
              onClick={(e) => {
                e.stopPropagation();
                fileInputRef.current?.click();
              }}
            >
              Upload Image
            </Button>
          </VStack>
        </Box>
      ) : (
        <VStack spacing={3} align="stretch">
          <Box border="2px solid" borderColor="green.300" borderRadius="lg" p={4} bg="green.50">
            <HStack justify="space-between" align="center">
              <HStack spacing={3} flex={1} minW={0}>
                <Icon as={AttachmentIcon} boxSize={6} color="green.600" />
                <VStack align="start" spacing={0} flex={1} minW={0}>
                  <Text fontSize="sm" fontWeight="semibold" color="green.800" isTruncated>
                    {file.name}
                  </Text>
                  <Text fontSize="xs" color="green.600">
                    {(file.size / 1024 / 1024).toFixed(2)} MB
                  </Text>
                </VStack>
              </HStack>
              <IconButton
                aria-label="Remove file"
                icon={<DeleteIcon />}
                size="sm"
                variant="ghost"
                colorScheme="red"
                isDisabled={disabled}
                onClick={() => onFileChange(null)}
              />
            </HStack>
          </Box>
          {previewUrl && (
            <Box borderRadius="md" overflow="hidden" border="1px" borderColor="gray.200">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={previewUrl} alt="Upload preview" style={{ maxWidth: "100%", display: "block" }} />
            </Box>
          )}
        </VStack>
      )}
    </FormControl>
  );
};

export default ImageInput;
