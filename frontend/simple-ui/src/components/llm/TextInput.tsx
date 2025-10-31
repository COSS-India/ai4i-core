// Text input component for LLM

import React from 'react';
import {
  Box,
  FormControl,
  FormLabel,
  Textarea,
  Button,
  HStack,
  Text,
} from '@chakra-ui/react';
import { TextInputProps } from '../../types/llm';

const TextInput: React.FC<TextInputProps> = ({
  inputText,
  onInputChange,
  onProcess,
  isLoading,
  inputLanguage,
  maxLength = 50000,
  disabled = false,
}) => {
  const remainingChars = maxLength - inputText.length;

  return (
    <Box>
      <FormControl>
        <HStack justify="space-between" mb={2}>
          <FormLabel mb={0}>Enter Text ({inputLanguage}):</FormLabel>
          <Text fontSize="sm" color={remainingChars < 100 ? 'red.500' : 'gray.600'}>
            {remainingChars} characters remaining
          </Text>
        </HStack>
        <Textarea
          value={inputText}
          onChange={(e) => onInputChange(e.target.value)}
          placeholder="Enter text to process..."
          size="lg"
          rows={8}
          resize="vertical"
          isDisabled={disabled || isLoading}
          maxLength={maxLength}
        />
      </FormControl>
      <Button
        mt={4}
        colorScheme="orange"
        onClick={onProcess}
        isLoading={isLoading}
        loadingText="Processing..."
        isDisabled={disabled || !inputText.trim() || isLoading}
        w="full"
      >
        Translate
      </Button>
    </Box>
  );
};

export default TextInput;

