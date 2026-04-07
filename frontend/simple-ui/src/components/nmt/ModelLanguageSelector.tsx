// Enhanced model and language selector component for NMT

import React, { useState, useEffect, useMemo } from 'react';
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
import { useAuth } from '../../hooks/useAuth';
import { LANG_CODE_TO_LABEL } from '../../config/constants';

interface ModelLanguageSelectorProps extends LanguageSelectorProps {
  selectedServiceId?: string;
  onServiceChange?: (serviceId: string) => void;
  hideServiceSelector?: boolean;
  /** When true, service dropdown is shown but disabled (e.g. anonymous users with fixed IndicTrans). */
  serviceDropdownDisabled?: boolean;
}

const ModelLanguageSelector: React.FC<ModelLanguageSelectorProps> = ({
  languagePair,
  onLanguagePairChange,
  availableLanguagePairs,
  loading = false,
  selectedServiceId,
  onServiceChange,
  hideServiceSelector = false,
  serviceDropdownDisabled = false,
}) => {
  const [currentServiceId, setCurrentServiceId] = useState<string>(selectedServiceId || '');
  const [availableLanguages, setAvailableLanguages] = useState<string[]>([]);
  const [languageDetails, setLanguageDetails] = useState<Array<{code: string; name: string}>>([]);
  const { isAuthenticated } = useAuth();

  // Fetch available services (key includes auth so we refetch after login and get published list, not cached anonymous IndicTrans)
  const { data: services, isLoading: servicesLoading } = useQuery({
    queryKey: ['nmt-services', isAuthenticated],
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

  // Update available languages when languages data changes; clear when null (e.g. service not found) to avoid stale options
  useEffect(() => {
    if (languagesData) {
      setAvailableLanguages(languagesData.supported_languages || []);
      setLanguageDetails(languagesData.language_details || []);
    } else if (currentServiceId) {
      setAvailableLanguages([]);
      setLanguageDetails([]);
    }
  }, [languagesData, currentServiceId]);

  // When current language pair is not in the new service's options, sync parent so state matches display and Translate uses correct languages
  useEffect(() => {
    if (!currentServiceId) return;
    const sourceIsEmpty = !languagePair.sourceLanguage?.trim();
    const targetIsEmpty = !languagePair.targetLanguage?.trim();

    // Don't auto-pick the first languages on initial load; keep placeholders ("Select")
    if (sourceIsEmpty && targetIsEmpty) return;

    const defaultCodes = Object.keys(LANG_CODE_TO_LABEL).sort((a, b) =>
      (LANG_CODE_TO_LABEL[a] || a).localeCompare(LANG_CODE_TO_LABEL[b] || b)
    );
    const options =
      availableLanguages.length > 0
        ? [...availableLanguages].sort((a, b) => {
            const getLabel = (code: string) => {
              const d = languageDetails.find((x) => x.code === code);
              return d ? d.name : code;
            };
            return getLabel(a).localeCompare(getLabel(b));
          })
        : defaultCodes;
    if (options.length === 0) return;
    const sourceValid = options.includes(languagePair.sourceLanguage);
    const targetValid = options.includes(languagePair.targetLanguage);
    if (sourceValid && targetValid) return;
    const newSource = sourceValid
      ? languagePair.sourceLanguage
      : sourceIsEmpty
        ? ''
        : (options[0] ?? '');
    const newTarget = targetValid
      ? languagePair.targetLanguage
      : targetIsEmpty
        ? ''
        : (options[1] ?? options[0] ?? '');
    onLanguagePairChange({
      ...languagePair,
      sourceLanguage: newSource,
      targetLanguage: newTarget,
      sourceScriptCode: '',
      targetScriptCode: '',
    });
  }, [currentServiceId, availableLanguages.length, languagePair.sourceLanguage, languagePair.targetLanguage, languageDetails.length]);

  // Sync with parent when selectedServiceId is set (e.g. anonymous users with fixed IndicTrans)
  useEffect(() => {
    if (selectedServiceId) {
      setCurrentServiceId(selectedServiceId);
    }
  }, [selectedServiceId]);

  // Do not auto-select a service; user must choose explicitly
  useEffect(() => {
    if (!services || services.length === 0) return;
    // keep currentServiceId as-is until user selects
  }, [services]);

  const handleServiceChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const serviceId = event.target.value;
    setCurrentServiceId(serviceId);
    if (onServiceChange) {
      onServiceChange(serviceId);
    }
  };

  const handleSourceLanguageChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const newSourceLanguage = event.target.value;
    const match = availableLanguagePairs?.find(
      (p) => p.sourceLanguage === newSourceLanguage && p.targetLanguage === languagePair.targetLanguage
    );
    onLanguagePairChange({
      ...languagePair,
      sourceLanguage: newSourceLanguage,
      sourceScriptCode: match?.sourceScriptCode ?? languagePair.sourceScriptCode,
      targetScriptCode: match?.targetScriptCode ?? languagePair.targetScriptCode,
    });
  };

  const handleTargetLanguageChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const newTargetLanguage = event.target.value;
    const match = availableLanguagePairs?.find(
      (p) => p.sourceLanguage === languagePair.sourceLanguage && p.targetLanguage === newTargetLanguage
    );
    onLanguagePairChange({
      ...languagePair,
      targetLanguage: newTargetLanguage,
      sourceScriptCode: match?.sourceScriptCode ?? languagePair.sourceScriptCode,
      targetScriptCode: match?.targetScriptCode ?? languagePair.targetScriptCode,
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
    // Prefer the shared constant mapping to keep UI consistent with LLM.
    const mapped = LANG_CODE_TO_LABEL[code];
    if (mapped) return String(mapped);

    const detail = languageDetails.find(d => d.code === code);
    return detail?.name ? String(detail.name) : String(code);
  };

  const isSwapAvailable = availableLanguages.includes(languagePair.sourceLanguage) &&
                          availableLanguages.includes(languagePair.targetLanguage) &&
                          languagePair.sourceLanguage !== languagePair.targetLanguage;

  // When no service selected, show default language list (always visible). When service selected, use service languages.
  const defaultLanguageCodes = Object.keys(LANG_CODE_TO_LABEL).sort((a, b) =>
    String(LANG_CODE_TO_LABEL[a] || a).localeCompare(String(LANG_CODE_TO_LABEL[b] || b))
  );
  const languageOptionsForDisplay =
    currentServiceId && availableLanguages.length > 0
      ? [...availableLanguages].sort((a, b) =>
          String(getLanguageLabel(a) || a).localeCompare(String(getLanguageLabel(b) || b))
        )
      : defaultLanguageCodes;

  // Ensure Select value is always in the options list to avoid client-side crash when switching to a model with different languages
  const safeSourceValue =
    languagePair.sourceLanguage?.trim() && languageOptionsForDisplay.includes(languagePair.sourceLanguage)
      ? languagePair.sourceLanguage
      : '';
  const targetLanguageOptionsForDisplay = useMemo(
    () => languageOptionsForDisplay.filter((langCode) => langCode !== safeSourceValue),
    [languageOptionsForDisplay, safeSourceValue]
  );
  const safeTargetValue =
    languagePair.targetLanguage?.trim() && targetLanguageOptionsForDisplay.includes(languagePair.targetLanguage)
      ? languagePair.targetLanguage
      : '';

  return (
    <Stack spacing={6} pt={0} mt={0}>
      {/* Service Selection - Hidden for anonymous users */}
      {!hideServiceSelector && (
        <>
          <Box pt={0} mt={0}>
            <FormControl mt={0} pt={0}>
              <FormLabel className="dview-service-try-option-title" mt={0}>
                NMT Service{" "}
                <Text as="span" color="red.500">*</Text>
              </FormLabel>
              <Select
                value={currentServiceId}
                onChange={handleServiceChange}
                placeholder="Select"
                disabled={servicesLoading || serviceDropdownDisabled}
              >
                {services?.map((service) => {
                  const version = service.modelVersion || service.model_version;
                  const displayText = version ? `${service.name || service.service_id} (${version})` : (service.name || service.service_id);
                  return (
                    <option key={service.service_id} value={service.service_id}>
                      {displayText}
                    </option>
                  );
                })}
              </Select>
            </FormControl>
            
            {selectedService && (
              <Box
                mt={2}
                p={3}
                bg="orange.50"
                borderRadius="md"
                border="1px"
                borderColor="orange.200"
              >
                <Text fontSize="sm" color="gray.700" mb={1}>
                  <strong>Service Name:</strong>{" "}
                  {selectedService.name || selectedService.service_id}
                </Text>
                <Text fontSize="sm" color="gray.700" mb={1}>
                  <strong>Service Description:</strong>{" "}
                  {selectedService.serviceDescription ||
                    selectedService.description ||
                    "No description available"}
                </Text>
              </Box>
            )}
          </Box>

          <Divider />
        </>
      )}

      {/* Language Selection - always visible; options from service when selected, else default list */}
      <Box>
        <Text className="dview-service-try-option-title" mb={4}>
          Language Configuration
        </Text>
        {languagesLoading && currentServiceId ? (
          <Stack spacing={2} align="center" py={4}>
            <Spinner size="md" color="orange.500" />
            <Text fontSize="sm" color="gray.600">Loading languages...</Text>
          </Stack>
        ) : (
          <Stack spacing={4}>
            <HStack spacing={4} align="end">
              {/* Source Language */}
              <FormControl flex={1}>
                <FormLabel fontSize="sm" color="gray.600" className="dview-service-try-option-title">
                  Source Language{" "}
                  <Text as="span" color="red.500">*</Text>
                </FormLabel>
                <Select
                  value={safeSourceValue}
                  onChange={handleSourceLanguageChange}
                  placeholder="Select"
                >
                  {languageOptionsForDisplay.map((langCode) => (
                    <option key={langCode} value={langCode}>
                      {getLanguageLabel(langCode)}
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
                <FormLabel fontSize="sm" color="gray.600" className="dview-service-try-option-title">
                  Target Language{" "}
                  <Text as="span" color="red.500">*</Text>
                </FormLabel>
                <Select
                  value={safeTargetValue}
                  onChange={handleTargetLanguageChange}
                  placeholder="Select"
                >
                  {targetLanguageOptionsForDisplay.map((langCode) => (
                    <option key={langCode} value={langCode}>
                      {getLanguageLabel(langCode)}
                    </option>
                  ))}
                </Select>
              </FormControl>
            </HStack>
          </Stack>
        )}
      </Box>
    </Stack>
  );
};

export default ModelLanguageSelector;
