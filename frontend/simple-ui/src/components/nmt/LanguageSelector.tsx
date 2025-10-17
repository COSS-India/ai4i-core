// Language pair selector component for NMT

import React from 'react';
import {
  Stack,
  FormControl,
  FormLabel,
  Select,
  IconButton,
  HStack,
  Text,
  Spinner,
} from '@chakra-ui/react';
import { FaExchangeAlt } from 'react-icons/fa';
import { LanguageSelectorProps } from '../../types/nmt';
import { LANG_CODE_TO_LABEL } from '../../config/constants';

const LanguageSelector: React.FC<LanguageSelectorProps> = ({
  languagePair,
  onLanguagePairChange,
  availableLanguagePairs,
  loading = false,
}) => {
  const handleLanguagePairChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    try {
      const selectedPair = JSON.parse(event.target.value);
      onLanguagePairChange(selectedPair);
    } catch (error) {
      console.error('Error parsing language pair:', error);
    }
  };

  const handleSwapLanguages = () => {
    const swappedPair = {
      sourceLanguage: languagePair.targetLanguage,
      targetLanguage: languagePair.sourceLanguage,
      sourceScriptCode: languagePair.targetScriptCode,
      targetScriptCode: languagePair.sourceScriptCode,
    };

    // Check if swapped pair is available
    const isSwappedPairAvailable = availableLanguagePairs.some(
      pair => 
        pair.sourceLanguage === swappedPair.sourceLanguage &&
        pair.targetLanguage === swappedPair.targetLanguage
    );

    if (isSwappedPairAvailable) {
      onLanguagePairChange(swappedPair);
    }
  };

  const getLanguagePairLabel = (pair: typeof languagePair) => {
    const sourceLabel = LANG_CODE_TO_LABEL[pair.sourceLanguage] || pair.sourceLanguage;
    const targetLabel = LANG_CODE_TO_LABEL[pair.targetLanguage] || pair.targetLanguage;
    return `${sourceLabel} → ${targetLabel}`;
  };

  const isSwapAvailable = availableLanguagePairs.some(
    pair => 
      pair.sourceLanguage === languagePair.targetLanguage &&
      pair.targetLanguage === languagePair.sourceLanguage
  );

  if (loading) {
    return (
      <Stack spacing={4} align="center" py={8}>
        <Spinner size="lg" color="orange.500" />
        <Text color="gray.600">Loading language pairs...</Text>
      </Stack>
    );
  }

  return (
    <Stack spacing={4}>
      <HStack spacing={4} align="end">
        {/* Language Pair Selection */}
        <FormControl flex={1}>
          <FormLabel className="dview-service-try-option-title">
            Languages:
          </FormLabel>
          <Select
            value={JSON.stringify(languagePair)}
            onChange={handleLanguagePairChange}
            placeholder="Choose language pair"
          >
            {availableLanguagePairs.map((pair, index) => (
              <option key={index} value={JSON.stringify(pair)}>
                {getLanguagePairLabel(pair)}
              </option>
            ))}
          </Select>
        </FormControl>

        {/* Swap Languages Button */}
        <IconButton
          aria-label="Swap languages"
          icon={<FaExchangeAlt />}
          onClick={handleSwapLanguages}
          isDisabled={!isSwapAvailable}
          variant="outline"
          size="md"
          colorScheme="orange"
        />
      </HStack>

      {/* Current Selection Display */}
      <Text fontSize="sm" color="gray.600" textAlign="center">
        {getLanguagePairLabel(languagePair)}
      </Text>
    </Stack>
  );
};

export default LanguageSelector;
