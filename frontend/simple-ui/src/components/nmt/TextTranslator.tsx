// Text translator component: source text input only (output shown on right panel)

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
import { TextTranslatorProps } from '../../types/nmt';
import { MAX_TEXT_LENGTH } from '../../config/constants';

const TextTranslator: React.FC<TextTranslatorProps> = ({
  inputText,
  onInputChange,
  maxLength = MAX_TEXT_LENGTH,
  disabled = false,
}) => {
  const [charCount, setCharCount] = useState(inputText.length);
  const [isInvalid, setIsInvalid] = useState(false);

  const borderColor = useColorModeValue('gray.300', 'gray.600');
  const invalidBorderColor = useColorModeValue('red.300', 'red.500');
  const counterColor = useColorModeValue('gray.500', 'gray.400');

  useEffect(() => {
    setCharCount(inputText.length);
    setIsInvalid(inputText.length > maxLength);
  }, [inputText, maxLength]);

  const handleInputChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    onInputChange(event.target.value);
  };

  const getCounterColor = () => {
    if (charCount > maxLength) return 'red.500';
    if (charCount > maxLength * 0.8) return 'orange.500';
    return counterColor;
  };

  return (
    <VStack spacing={5} w="full" align="stretch">
      <FormControl isInvalid={isInvalid}>
        <FormLabel fontSize="sm" fontWeight="semibold" color="gray.700">
          Source Text{" "}
          <Text as="span" color="red.500">*</Text>
        </FormLabel>
        <Textarea
          value={inputText}
          onChange={handleInputChange}
          placeholder="Type your text here to translate..."
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

      <Box display="flex" justifyContent="flex-end">
        <Text
          fontSize="sm"
          color={getCounterColor()}
          fontWeight={charCount > maxLength ? 'semibold' : 'normal'}
        >
          {charCount}/{maxLength}
        </Text>
      </Box>
    </VStack>
  );
};

export default TextTranslator;
