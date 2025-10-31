// Language selector component for LLM

import React from 'react';
import {
  Stack,
  FormControl,
  FormLabel,
  Select,
  IconButton,
  HStack,
} from '@chakra-ui/react';
import { FaExchangeAlt } from 'react-icons/fa';
import { LanguageSelectorProps } from '../../types/llm';
import { LANG_CODE_TO_LABEL } from '../../config/constants';

const LanguageSelector: React.FC<LanguageSelectorProps> = ({
  inputLanguage,
  outputLanguage,
  onInputLanguageChange,
  onOutputLanguageChange,
  availableLanguages,
}) => {
  const handleSwapLanguages = () => {
    const temp = inputLanguage;
    onInputLanguageChange(outputLanguage);
    onOutputLanguageChange(temp);
  };

  return (
    <Stack spacing={4}>
      <HStack spacing={4} align="end">
        <FormControl flex={1}>
          <FormLabel>Input Language:</FormLabel>
          <Select
            value={inputLanguage}
            onChange={(e) => onInputLanguageChange(e.target.value)}
          >
            {availableLanguages.map((lang) => (
              <option key={lang} value={lang}>
                {LANG_CODE_TO_LABEL[lang] || lang}
              </option>
            ))}
          </Select>
        </FormControl>

        <IconButton
          aria-label="Swap languages"
          icon={<FaExchangeAlt />}
          onClick={handleSwapLanguages}
          size="md"
          colorScheme="orange"
          variant="outline"
        />

        <FormControl flex={1}>
          <FormLabel>Output Language:</FormLabel>
          <Select
            value={outputLanguage}
            onChange={(e) => onOutputLanguageChange(e.target.value)}
          >
            {availableLanguages.map((lang) => (
              <option key={lang} value={lang}>
                {LANG_CODE_TO_LABEL[lang] || lang}
              </option>
            ))}
          </Select>
        </FormControl>
      </HStack>
    </Stack>
  );
};

export default LanguageSelector;

