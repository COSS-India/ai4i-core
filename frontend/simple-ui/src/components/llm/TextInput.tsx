// Text input component for LLM with character count and validation

import React, { useEffect, useState } from 'react';
import {
  Box,
  FormControl,
  FormErrorMessage,
  FormLabel,
  Textarea,
  Text,
  useColorModeValue,
} from '@chakra-ui/react';
import { TextInputProps } from '../../types/llm';

const TextInput: React.FC<TextInputProps> = ({
  inputText,
  onInputChange,
  maxLength = 50000,
  disabled = false,
}) => {
  const [isInvalid, setIsInvalid] = useState(inputText.length > maxLength);
  const borderColor = useColorModeValue('gray.300', 'gray.600');
  const invalidBorderColor = useColorModeValue('red.300', 'red.500');
  const counterColor = useColorModeValue('gray.500', 'gray.400');

  useEffect(() => {
    setIsInvalid(inputText.length > maxLength);
  }, [inputText.length, maxLength]);

  const charCount = inputText.length;
  const getCounterColor = () => {
    if (charCount > maxLength) return 'red.500';
    if (charCount > maxLength * 0.8) return 'orange.500';
    return counterColor;
  };

  return (
    <Box>
      <FormControl isInvalid={isInvalid}>
        <FormLabel fontSize="sm" color="gray.600" className="dview-service-try-option-title">
          Source Text{" "}
          <Text as="span" color="red.500">*</Text>
        </FormLabel>
        <Textarea
          mt={2}
          value={inputText}
          onChange={(e) => onInputChange(e.target.value)}
          placeholder="Enter text to process..."
          size="lg"
          rows={8}
          resize="vertical"
          isDisabled={disabled}
          maxLength={maxLength}
          borderColor={isInvalid ? invalidBorderColor : borderColor}
          _focus={{
            boxShadow: 'none',
            borderColor: isInvalid ? invalidBorderColor : 'orange.300',
          }}
        />
        {isInvalid && (
          <FormErrorMessage>
            Text length ({charCount}) exceeds maximum limit of {maxLength} characters.
          </FormErrorMessage>
        )}
      </FormControl>
      <Box display="flex" justifyContent="flex-end" mt={1}>
        <Text
          fontSize="sm"
          color={getCounterColor()}
          fontWeight={charCount > maxLength ? 'semibold' : 'normal'}
        >
          {charCount} / {maxLength}
        </Text>
      </Box>
    </Box>
  );
};

export default TextInput;

