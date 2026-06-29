// Unified text input for AI service request panels

import React, { useEffect, useState } from "react";
import {
  Box,
  FormControl,
  FormErrorMessage,
  FormLabel,
  Text,
  Textarea,
  useColorModeValue,
} from "@chakra-ui/react";
import { MAX_TEXT_LENGTH } from '../../../constants';
import type { ServiceTextInputProps } from "../../../types/servicePage";

const TextInput: React.FC<ServiceTextInputProps> = ({
  value,
  onChange,
  label = "Source Text",
  placeholder = "Enter text...",
  maxLength = MAX_TEXT_LENGTH,
  disabled = false,
  required = true,
  rows = 8,
  showCharCounter = true,
  resize = "vertical",
}) => {
  const [isInvalid, setIsInvalid] = useState(value.length > maxLength);
  const borderColor = useColorModeValue("gray.300", "gray.600");
  const invalidBorderColor = useColorModeValue("red.300", "red.500");
  const counterColor = useColorModeValue("gray.500", "gray.400");

  useEffect(() => {
    setIsInvalid(value.length > maxLength);
  }, [value.length, maxLength]);

  const charCount = value.length;
  const getCounterColor = () => {
    if (charCount > maxLength) return "red.500";
    if (charCount > maxLength * 0.8) return "orange.500";
    return counterColor;
  };

  return (
    <Box>
      <FormControl isInvalid={isInvalid}>
        <FormLabel
          fontSize="sm"
          fontWeight="semibold"
          color="gray.700"
          className="dview-service-try-option-title"
        >
          {label}{" "}
          {required && (
            <Text as="span" color="red.500">
              *
            </Text>
          )}
        </FormLabel>
        <Textarea
          mt={2}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          resize={resize}
          rows={rows}
          isDisabled={disabled}
          maxLength={maxLength}
          borderColor={isInvalid ? invalidBorderColor : borderColor}
          _focus={{
            boxShadow: "none",
            borderColor: isInvalid ? invalidBorderColor : "orange.300",
          }}
        />
        {isInvalid && (
          <FormErrorMessage>
            Text length ({charCount}) exceeds maximum limit of {maxLength} characters.
          </FormErrorMessage>
        )}
      </FormControl>
      {showCharCounter && (
        <Box display="flex" justifyContent="flex-end" mt={1}>
          <Text
            fontSize="sm"
            color={getCounterColor()}
            fontWeight={charCount > maxLength ? "semibold" : "normal"}
          >
            {charCount} / {maxLength}
          </Text>
        </Box>
      )}
    </Box>
  );
};

export default TextInput;
