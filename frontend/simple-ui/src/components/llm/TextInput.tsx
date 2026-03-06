// Text input component for LLM

import React from 'react';
import {
  Box,
  FormControl,
  FormLabel,
  Textarea,
  Text,
} from '@chakra-ui/react';
import { TextInputProps } from '../../types/llm';

const TextInput: React.FC<TextInputProps> = ({
  inputText,
  onInputChange,
  maxLength = 50000,
  disabled = false,
}) => {
  return (
    <Box>
      <FormControl>
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
        />
      </FormControl>
    </Box>
  );
};

export default TextInput;

