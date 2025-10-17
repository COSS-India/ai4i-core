// Text translator component with input and output textareas

import React, { useState, useEffect } from 'react';
import {
  VStack,
  Textarea,
  Button,
  HStack,
  Text,
  Box,
  FormControl,
  FormLabel,
  FormErrorMessage,
  useColorModeValue,
  Spinner,
} from '@chakra-ui/react';
import { FaLanguage } from 'react-icons/fa';
import { TextTranslatorProps } from '../../types/nmt';
import { MAX_TEXT_LENGTH } from '../../config/constants';

const TextTranslator: React.FC<TextTranslatorProps> = ({
  inputText,
  translatedText,
  onInputChange,
  onTranslate,
  isLoading,
  sourceLanguage,
  maxLength = MAX_TEXT_LENGTH,
  disabled = false,
}) => {
  const [charCount, setCharCount] = useState(inputText.length);
  const [isInvalid, setIsInvalid] = useState(false);

  const borderColor = useColorModeValue('gray.300', 'gray.600');
  const invalidBorderColor = useColorModeValue('red.300', 'red.500');
  const counterColor = useColorModeValue('gray.500', 'gray.400');

  // Update character count when input changes
  useEffect(() => {
    setCharCount(inputText.length);
    setIsInvalid(inputText.length > maxLength);
  }, [inputText, maxLength]);

  const handleInputChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newValue = event.target.value;
    onInputChange(newValue);
  };

  const handleTranslate = () => {
    if (inputText.trim() && !isInvalid && !isLoading) {
      onTranslate();
    }
  };

  const getCounterColor = () => {
    if (charCount > maxLength) return 'red.500';
    if (charCount > maxLength * 0.8) return 'orange.500';
    return counterColor;
  };

  return (
    <VStack spacing={5} w="full" align="stretch">
      {/* Input Textarea */}
      <FormControl isInvalid={isInvalid}>
        <FormLabel fontSize="sm" fontWeight="semibold" color="gray.700">
          Source Text
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

      {/* Translate Button */}
      <Button
        leftIcon={isLoading ? <Spinner size="sm" /> : <FaLanguage />}
        colorScheme="orange"
        onClick={handleTranslate}
        isDisabled={!inputText.trim() || isInvalid || isLoading || disabled}
        isLoading={isLoading}
        loadingText="Translating..."
        size="lg"
        w="full"
      >
        Translate
      </Button>

      {/* Output Textarea */}
      <FormControl>
        <FormLabel fontSize="sm" fontWeight="semibold" color="gray.700">
          Translation
        </FormLabel>
        <Textarea
          value={translatedText}
          readOnly
          placeholder="View Translation Here..."
          resize="none"
          h="200px"
          bg={useColorModeValue('gray.50', 'gray.700')}
          borderColor={borderColor}
          _focus={{
            boxShadow: 'none',
            borderColor: 'orange.300',
          }}
        />
      </FormControl>

      {/* Language Info */}
      {sourceLanguage && (
        <Text fontSize="xs" color="gray.500" textAlign="center">
          Source Language: {sourceLanguage}
        </Text>
      )}
    </VStack>
  );
};

export default TextTranslator;
