// Text input component for LLM

import React from 'react';
import {
  Box,
  FormControl,
  Textarea,
  Button,
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
  return (
    <Box>
      <FormControl>
        <Textarea
          mt={2}
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

