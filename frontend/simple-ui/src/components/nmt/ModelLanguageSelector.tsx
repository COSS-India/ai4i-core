// Enhanced model and language selector component for NMT

import React, { useState, useEffect } from 'react';
import {
  Stack,
  FormControl,
  FormLabel,
  Select,
  IconButton,
  HStack,
  Text,
  Spinner,
  Box,
  Divider,
  Badge,
} from '@chakra-ui/react';
import { FaExchangeAlt, FaInfoCircle } from 'react-icons/fa';
import { useQuery } from '@tanstack/react-query';
import { LanguageSelectorProps } from '../../types/nmt';
import { LANG_CODE_TO_LABEL } from '../../config/constants';
import { listNMTModels, getNMTLanguages } from '../../services/nmtService';
import { NMTModelDetailsResponse, NMTLanguagesResponse } from '../../types/nmt';

interface ModelLanguageSelectorProps extends LanguageSelectorProps {
  selectedModelId?: string;
  onModelChange?: (modelId: string) => void;
}

const ModelLanguageSelector: React.FC<ModelLanguageSelectorProps> = ({
  languagePair,
  onLanguagePairChange,
  availableLanguagePairs,
  loading = false,
  selectedModelId,
  onModelChange,
}) => {
  const [currentModelId, setCurrentModelId] = useState<string>(selectedModelId || '');
  const [availableLanguages, setAvailableLanguages] = useState<string[]>([]);
  const [languageDetails, setLanguageDetails] = useState<Array<{code: string; name: string}>>([]);

  // Fetch available models
  const { data: models, isLoading: modelsLoading } = useQuery({
    queryKey: ['nmt-models'],
    queryFn: listNMTModels,
    staleTime: 10 * 60 * 1000, // 10 minutes
  });

  // Fetch languages for selected model
  const { data: languagesData, isLoading: languagesLoading } = useQuery({
    queryKey: ['nmt-languages', currentModelId],
    queryFn: () => getNMTLanguages(currentModelId || undefined),
    enabled: !!currentModelId,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  // Update available languages when languages data changes
  useEffect(() => {
    if (languagesData) {
      setAvailableLanguages(languagesData.supported_languages);
      setLanguageDetails(languagesData.language_details);
    }
  }, [languagesData]);

  // Set default model when models are loaded
  useEffect(() => {
    if (models && models.length > 0 && !currentModelId) {
      const defaultModel = models[0];
      setCurrentModelId(defaultModel.model_id);
      if (onModelChange) {
        onModelChange(defaultModel.model_id);
      }
    }
  }, [models, currentModelId, onModelChange]);

  const handleModelChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const modelId = event.target.value;
    setCurrentModelId(modelId);
    if (onModelChange) {
      onModelChange(modelId);
    }
  };

  const handleSourceLanguageChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const newSourceLanguage = event.target.value;
    onLanguagePairChange({
      ...languagePair,
      sourceLanguage: newSourceLanguage,
    });
  };

  const handleTargetLanguageChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const newTargetLanguage = event.target.value;
    onLanguagePairChange({
      ...languagePair,
      targetLanguage: newTargetLanguage,
    });
  };

  const handleSwapLanguages = () => {
    const swappedPair = {
      sourceLanguage: languagePair.targetLanguage,
      targetLanguage: languagePair.sourceLanguage,
      sourceScriptCode: languagePair.targetScriptCode,
      targetScriptCode: languagePair.sourceScriptCode,
    };

    // Check if both languages are available in current model
    const isSwappedPairAvailable = availableLanguages.includes(swappedPair.sourceLanguage) &&
                                   availableLanguages.includes(swappedPair.targetLanguage);

    if (isSwappedPairAvailable) {
      onLanguagePairChange(swappedPair);
    }
  };

  const getLanguageLabel = (code: string) => {
    const detail = languageDetails.find(d => d.code === code);
    return detail ? detail.name : (LANG_CODE_TO_LABEL[code] || code);
  };

  const isSwapAvailable = availableLanguages.includes(languagePair.sourceLanguage) &&
                          availableLanguages.includes(languagePair.targetLanguage) &&
                          languagePair.sourceLanguage !== languagePair.targetLanguage;

  const selectedModel = models?.find(m => m.model_id === currentModelId);

  if (loading || modelsLoading) {
    return (
      <Stack spacing={4} align="center" py={8}>
        <Spinner size="lg" color="orange.500" />
        <Text color="gray.600">Loading models and languages...</Text>
      </Stack>
    );
  }

  return (
    <Stack spacing={6}>
      {/* Model Selection */}
      <Box>
        <FormControl>
          <FormLabel className="dview-service-try-option-title">
            Translation Model:
          </FormLabel>
          <Select
            value={currentModelId}
            onChange={handleModelChange}
            placeholder="Select a model"
            disabled={modelsLoading}
          >
            {models?.map((model) => (
              <option key={model.model_id} value={model.model_id}>
                {model.model_id} ({model.provider})
              </option>
            ))}
          </Select>
        </FormControl>
        
        {selectedModel && (
          <Box mt={2} p={3} bg="gray.50" borderRadius="md">
            <Text fontSize="sm" color="gray.600" mb={1}>
              <strong>Provider:</strong> {selectedModel.provider}
            </Text>
            <Text fontSize="sm" color="gray.600" mb={1}>
              <strong>Description:</strong> {selectedModel.description}
            </Text>
            <Text fontSize="sm" color="gray.600" mb={1}>
              <strong>Max Batch Size:</strong> {selectedModel.max_batch_size}
            </Text>
            <HStack spacing={2} wrap="wrap">
              <Text fontSize="sm" color="gray.600">
                <strong>Supported Scripts:</strong>
              </Text>
              {selectedModel.supported_scripts.map((script) => (
                <Badge key={script} colorScheme="blue" size="sm">
                  {script}
                </Badge>
              ))}
            </HStack>
          </Box>
        )}
      </Box>

      <Divider />

      {/* Language Selection */}
      <Box>
        <Text className="dview-service-try-option-title" mb={4}>
          Language Configuration
        </Text>
        
        {languagesLoading ? (
          <Stack spacing={2} align="center" py={4}>
            <Spinner size="md" color="orange.500" />
            <Text fontSize="sm" color="gray.600">Loading languages...</Text>
          </Stack>
        ) : (
          <Stack spacing={4}>
            <HStack spacing={4} align="end">
              {/* Source Language */}
              <FormControl flex={1}>
                <FormLabel fontSize="sm" color="gray.600">
                  From:
                </FormLabel>
                <Select
                  value={languagePair.sourceLanguage}
                  onChange={handleSourceLanguageChange}
                  placeholder="Select source language"
                >
                  {availableLanguages.map((langCode) => (
                    <option key={langCode} value={langCode}>
                      {getLanguageLabel(langCode)} ({langCode})
                    </option>
                  ))}
                </Select>
              </FormControl>

              {/* Swap Button */}
              <IconButton
                aria-label="Swap languages"
                icon={<FaExchangeAlt />}
                onClick={handleSwapLanguages}
                isDisabled={!isSwapAvailable}
                variant="outline"
                size="md"
                colorScheme="orange"
              />

              {/* Target Language */}
              <FormControl flex={1}>
                <FormLabel fontSize="sm" color="gray.600">
                  To:
                </FormLabel>
                <Select
                  value={languagePair.targetLanguage}
                  onChange={handleTargetLanguageChange}
                  placeholder="Select target language"
                >
                  {availableLanguages.map((langCode) => (
                    <option key={langCode} value={langCode}>
                      {getLanguageLabel(langCode)} ({langCode})
                    </option>
                  ))}
                </Select>
              </FormControl>
            </HStack>

            {/* Current Selection Display */}
            <Box textAlign="center" p={3} bg="orange.50" borderRadius="md">
              <Text fontSize="sm" color="orange.700" fontWeight="medium">
                {getLanguageLabel(languagePair.sourceLanguage)} → {getLanguageLabel(languagePair.targetLanguage)}
              </Text>
              <Text fontSize="xs" color="orange.600" mt={1}>
                {languagePair.sourceLanguage} → {languagePair.targetLanguage}
              </Text>
            </Box>

            {/* Language Count Info */}
            <HStack justify="center" spacing={4}>
              <HStack spacing={1}>
                <FaInfoCircle size={12} color="#718096" />
                <Text fontSize="xs" color="gray.500">
                  {availableLanguages.length} languages supported
                </Text>
              </HStack>
              <Text fontSize="xs" color="gray.400">•</Text>
              <Text fontSize="xs" color="gray.500">
                {availableLanguages.length * (availableLanguages.length - 1)} possible pairs
              </Text>
            </HStack>
          </Stack>
        )}
      </Box>
    </Stack>
  );
};

export default ModelLanguageSelector;
