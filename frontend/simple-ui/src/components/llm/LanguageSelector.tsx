// Language selector component for LLM

import React, { useMemo } from 'react';
import {
  Stack,
  FormControl,
  FormLabel,
  Select,
  IconButton,
  HStack,
  Text,
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

  const sortedLanguages = [...availableLanguages].sort((a, b) => {
    const labelA = LANG_CODE_TO_LABEL[a] || a;
    const labelB = LANG_CODE_TO_LABEL[b] || b;
    return labelA.localeCompare(labelB);
  });
  const targetLanguageOptions = useMemo(
    () => sortedLanguages.filter((lang) => lang !== inputLanguage),
    [sortedLanguages, inputLanguage]
  );
  const safeOutputLanguage = targetLanguageOptions.includes(outputLanguage) ? outputLanguage : '';

  return (
    <Stack spacing={4}>
      <HStack spacing={4} align="end">
        <FormControl flex={1}>
          <FormLabel fontSize="sm" color="gray.600" className="dview-service-try-option-title">
            Source Language{" "}
            <Text as="span" color="red.500">*</Text>
          </FormLabel>
          <Select
            value={inputLanguage}
            onChange={(e) => onInputLanguageChange(e.target.value)}
            placeholder="Select"
          >
            {sortedLanguages.map((lang) => (
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
          <FormLabel fontSize="sm" color="gray.600" className="dview-service-try-option-title">
            Target Language{" "}
            <Text as="span" color="red.500">*</Text>
          </FormLabel>
          <Select
            value={safeOutputLanguage}
            onChange={(e) => onOutputLanguageChange(e.target.value)}
            placeholder="Select"
          >
            {targetLanguageOptions.map((lang) => (
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

