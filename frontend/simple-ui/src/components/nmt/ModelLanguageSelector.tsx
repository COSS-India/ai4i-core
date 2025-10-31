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
import { listNMTServices, getNMTLanguagesForService } from '../../services/nmtService';
import { NMTServiceDetailsResponse, NMTLanguagesResponse } from '../../types/nmt';

interface ModelLanguageSelectorProps extends LanguageSelectorProps {
  selectedServiceId?: string;
  onServiceChange?: (serviceId: string) => void;
}

const ModelLanguageSelector: React.FC<ModelLanguageSelectorProps> = ({
  languagePair,
  onLanguagePairChange,
  availableLanguagePairs,
  loading = false,
  selectedServiceId,
  onServiceChange,
}) => {
  const [currentServiceId, setCurrentServiceId] = useState<string>(selectedServiceId || '');
  const [availableLanguages, setAvailableLanguages] = useState<string[]>([]);
  const [languageDetails, setLanguageDetails] = useState<Array<{code: string; name: string}>>([]);

  // Fetch available services
  const { data: services, isLoading: servicesLoading } = useQuery({
    queryKey: ['nmt-services'],
    queryFn: listNMTServices,
    staleTime: 10 * 60 * 1000, // 10 minutes
  });

  // Find selected service
  const selectedService = services?.find(s => s.service_id === currentServiceId);

  // Fetch languages for selected service
  const { data: languagesData, isLoading: languagesLoading } = useQuery({
    queryKey: ['nmt-languages', currentServiceId],
    queryFn: () => getNMTLanguagesForService(currentServiceId),
    enabled: !!currentServiceId,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  // Update available languages when languages data changes
  useEffect(() => {
    if (languagesData) {
      setAvailableLanguages(languagesData.supported_languages || []);
      setLanguageDetails(languagesData.language_details || []);
    }
  }, [languagesData]);

  // Set default service when services are loaded
  useEffect(() => {
    if (services && services.length > 0 && !currentServiceId) {
      const defaultService = services[0];
      setCurrentServiceId(defaultService.service_id);
      if (onServiceChange) {
        onServiceChange(defaultService.service_id);
      }
    }
  }, [services, currentServiceId, onServiceChange]);

  const handleServiceChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const serviceId = event.target.value;
    setCurrentServiceId(serviceId);
    if (onServiceChange) {
      onServiceChange(serviceId);
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
    return detail ? detail.name : code;
  };

  const isSwapAvailable = availableLanguages.includes(languagePair.sourceLanguage) &&
                          availableLanguages.includes(languagePair.targetLanguage) &&
                          languagePair.sourceLanguage !== languagePair.targetLanguage;

  if (loading || servicesLoading) {
    return (
      <Stack spacing={4} align="center" py={8}>
        <Spinner size="lg" color="orange.500" />
        <Text color="gray.600">Loading services and languages...</Text>
      </Stack>
    );
  }

  return (
    <Stack spacing={6}>
      {/* Service Selection */}
      <Box>
        <FormControl>
          <FormLabel className="dview-service-try-option-title">
            Translation Service:
          </FormLabel>
          <Select
            value={currentServiceId}
            onChange={handleServiceChange}
            placeholder="Select a service"
            disabled={servicesLoading}
          >
            {services?.map((service) => (
              <option key={service.service_id} value={service.service_id}>
                {service.service_id} ({service.provider})
              </option>
            ))}
          </Select>
        </FormControl>
        
        {selectedService && (
          <Box mt={2} p={3} bg="gray.50" borderRadius="md">
            <Text fontSize="sm" color="gray.600" mb={1}>
              <strong>Service ID:</strong> {selectedService.service_id}
            </Text>
            <Text fontSize="sm" color="gray.600" mb={1}>
              <strong>Provider:</strong> {selectedService.provider}
            </Text>
            <Text fontSize="sm" color="gray.600" mb={1}>
              <strong>Description:</strong> {selectedService.description}
            </Text>
            <Text fontSize="sm" color="gray.600" mb={1}>
              <strong>Model:</strong> {selectedService.model_id}
            </Text>
            <Text fontSize="sm" color="gray.600" mb={1}>
              <strong>Triton Endpoint:</strong> {selectedService.triton_endpoint}
            </Text>
            <Text fontSize="sm" color="gray.600" mb={1}>
              <strong>Supported Languages:</strong> {selectedService.supported_languages.length}
            </Text>
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
