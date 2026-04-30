// Text input component for TTS with character count and validation

import React, { useState, useEffect } from 'react';
import {
  VStack,
  Textarea,
  Text,
  Box,
  FormControl,
  FormLabel,
  FormErrorMessage,
  useColorModeValue,
} from '@chakra-ui/react';
import { TextInputProps } from '../../types/tts';
import { MAX_TEXT_LENGTH } from '../../config/constants';

const TextInput: React.FC<TextInputProps> = ({
  value,
  onChange,
  language,
  maxLength = MAX_TEXT_LENGTH,
  placeholder = 'Enter text to synthesize...',
  disabled = false,
}) => {
  const [charCount, setCharCount] = useState(value.length);
  const [isInvalid, setIsInvalid] = useState(false);

  const borderColor = useColorModeValue('gray.300', 'gray.600');
  const invalidBorderColor = useColorModeValue('red.300', 'red.500');
  const counterColor = useColorModeValue('gray.500', 'gray.400');

  // Update character count when value changes
  useEffect(() => {
    setCharCount(value.length);
    setIsInvalid(value.length > maxLength);
  }, [value, maxLength]);

  const handleChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newValue = event.target.value;
    onChange(newValue);
  };

  const getCounterColor = () => {
    if (charCount > maxLength) return 'red.500';
    if (charCount > maxLength * 0.8) return 'orange.500';
    return counterColor;
  };

  return (
    <VStack spacing={3} w="full" align="stretch">
      <FormControl isInvalid={isInvalid}>
        <FormLabel fontSize="sm" fontWeight="semibold" color="gray.700">
          Text Input
        </FormLabel>
        <Textarea
          value={value}
          onChange={handleChange}
          placeholder={placeholder}
          resize="none"
          h="200px"
          disabled={disabled}
          borderColor={isInvalid ? invalidBorderColor : borderColor}
          _focus={{
            boxShadow: 'none',
            borderColor: isInvalid ? invalidBorderColor : 'orange.300',
          }}
          _hover={{
            borderColor: isInvalid ? invalidBorderColor : 'gray.400',
          }}
        />
        {isInvalid && (
          <FormErrorMessage>
            Text length ({charCount}) exceeds maximum limit of {maxLength} characters.
          </FormErrorMessage>
        )}
      </FormControl>

      {/* Character Counter */}
      <Box display="flex" justifyContent="flex-end">
        <Text
          fontSize="sm"
          color={getCounterColor()}
          fontWeight={charCount > maxLength ? 'semibold' : 'normal'}
        >
          {charCount}/{maxLength}
        </Text>
      </Box>

      {/* Language Info */}
      {language && (
        <Text fontSize="xs" color="gray.500" textAlign="center">
          Language: {language}
        </Text>
      )}
    </VStack>
  );
};

export default TextInput;
