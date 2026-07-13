// Reusable service/model selector for AI service pages

import React from "react";
import {
  Alert,
  AlertDescription,
  AlertIcon,
  Box,
  FormControl,
  FormLabel,
  Select,
  Text,
  VStack,
} from "@chakra-ui/react";
import type { ServiceDropdownProps } from "../../types/servicePage";
import { LABELS } from "../../constants";

const ServiceDropdown: React.FC<ServiceDropdownProps> = ({
  label = "Service",
  required = true,
  value,
  onChange,
  options,
  loading = false,
  disabled = false,
  placeholder,
  error,
  showSelectedDetails = true,
}) => {
  const selected = options.find((o) => o.id === value);
  const displayPlaceholder =
    placeholder ?? (loading ? LABELS.STATUS.LOADING : "Select");

  return (
    <VStack spacing={2} align="stretch">
      <FormControl>
        <FormLabel fontSize="sm" fontWeight="semibold" className="dview-service-try-option-title">
          {label}{" "}
          {required && (
            <Text as="span" color="red.500">
              *
            </Text>
          )}
        </FormLabel>
        <Select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          isDisabled={disabled || loading}
          placeholder={displayPlaceholder}
          size="md"
          borderColor="gray.300"
          _focus={{
            borderColor: "orange.400",
            boxShadow: "0 0 0 1px var(--chakra-colors-orange-400)",
          }}
        >
          {options.map((option) => {
            const displayText = option.version
              ? `${option.label} (${option.version})`
              : option.label;
            return (
              <option key={option.id} value={option.id}>
                {displayText}
              </option>
            );
          })}
        </Select>
      </FormControl>

      {error && (
        <Alert status="error" borderRadius="md">
          <AlertIcon />
          <AlertDescription fontSize="sm">{error}</AlertDescription>
        </Alert>
      )}

      {showSelectedDetails && selected && (selected.description || selected.label) && (
        <Box
          p={3}
          bg="orange.50"
          borderRadius="md"
          border="1px"
          borderColor="orange.200"
        >
          <Text fontSize="sm" color="gray.700" mb={selected.description ? 1 : 0}>
            <strong>Service Name:</strong> {selected.label}
          </Text>
          {selected.description && (
            <Text fontSize="sm" color="gray.700">
              <strong>Service Description:</strong> {selected.description}
            </Text>
          )}
        </Box>
      )}
    </VStack>
  );
};

export default ServiceDropdown;
