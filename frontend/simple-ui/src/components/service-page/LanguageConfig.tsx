// Source/target language selection with swap support for service pages

import React from "react";
import {
  FormControl,
  FormLabel,
  HStack,
  IconButton,
  Select,
  Spinner,
  Stack,
  Text,
  VStack,
} from "@chakra-ui/react";
import { FaExchangeAlt } from "react-icons/fa";
import type {
  LanguageConfigProps,
  LanguagePairOption,
} from "../../types/servicePage";

const defaultPairLabel = (pair: LanguagePairOption) =>
  `${pair.sourceLanguage} → ${pair.targetLanguage}`;

const LanguageConfig: React.FC<LanguageConfigProps> = ({
  mode,
  loading = false,
  disabled = false,
  sourceLanguage = "",
  targetLanguage = "",
  onSourceChange,
  onTargetChange,
  sourceOptions = [],
  targetOptions = [],
  onSwap,
  swapDisabled = false,
  languagePair,
  onLanguagePairChange,
  languagePairOptions = [],
  getLanguagePairLabel = defaultPairLabel,
}) => {
  if (mode === "none") return null;

  if (loading) {
    return (
      <Stack spacing={4} align="center" py={4}>
        <Spinner size="lg" color="orange.500" />
        <Text color="gray.600" fontSize="sm">
          Loading languages...
        </Text>
      </Stack>
    );
  }

  if (mode === "language-pair" && languagePair && onLanguagePairChange) {
    const handlePairChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
      try {
        const selected = JSON.parse(event.target.value) as LanguagePairOption;
        onLanguagePairChange(selected);
      } catch (err) {
        console.error("Error parsing language pair:", err);
      }
    };

    const isSwapAvailable = languagePairOptions.some(
      (p) =>
        p.sourceLanguage === languagePair.targetLanguage &&
        p.targetLanguage === languagePair.sourceLanguage,
    );

    const handleSwap = () => {
      if (!onSwap) {
        const swapped: LanguagePairOption = {
          sourceLanguage: languagePair.targetLanguage,
          targetLanguage: languagePair.sourceLanguage,
          sourceScriptCode: languagePair.targetScriptCode,
          targetScriptCode: languagePair.sourceScriptCode,
        };
        if (isSwapAvailable) onLanguagePairChange(swapped);
        return;
      }
      onSwap();
    };

    return (
      <Stack spacing={4}>
        <HStack spacing={4} align="end">
          <FormControl flex={1}>
            <FormLabel
              className="dview-service-try-option-title"
              fontSize="sm"
              fontWeight="semibold"
            >
              Languages
            </FormLabel>
            <Select
              value={JSON.stringify(languagePair)}
              onChange={handlePairChange}
              placeholder="Select"
              isDisabled={disabled}
            >
              {languagePairOptions.map((pair, index) => (
                <option key={index} value={JSON.stringify(pair)}>
                  {getLanguagePairLabel(pair)}
                </option>
              ))}
            </Select>
          </FormControl>
          <IconButton
            aria-label="Swap languages"
            icon={<FaExchangeAlt />}
            onClick={handleSwap}
            isDisabled={disabled || swapDisabled || !isSwapAvailable}
            variant="outline"
            size="md"
            colorScheme="orange"
          />
        </HStack>
        <Text fontSize="sm" color="gray.600" textAlign="center">
          {getLanguagePairLabel(languagePair)}
        </Text>
      </Stack>
    );
  }

  if (mode === "source-only") {
    return (
      <FormControl>
        <FormLabel
          className="dview-service-try-option-title"
          fontSize="sm"
          fontWeight="semibold"
        >
          Language{" "}
          <Text as="span" color="red.500">
            *
          </Text>
        </FormLabel>
        <Select
          value={sourceLanguage}
          onChange={(e) => onSourceChange?.(e.target.value)}
          placeholder="Select"
          isDisabled={disabled}
        >
          {sourceOptions.map((lang) => (
            <option key={lang.code} value={lang.code}>
              {lang.label}
            </option>
          ))}
        </Select>
      </FormControl>
    );
  }

  if (mode === "source-target") {
    return (
      <VStack spacing={4} align="stretch">
        <HStack spacing={4} align="end">
          <FormControl flex={1}>
            <FormLabel
              fontSize="sm"
              fontWeight="semibold"
              className="dview-service-try-option-title"
            >
              Source Language{" "}
              <Text as="span" color="red.500">
                *
              </Text>
            </FormLabel>
            <Select
              value={sourceLanguage}
              onChange={(e) => onSourceChange?.(e.target.value)}
              placeholder="Select"
              isDisabled={disabled}
            >
              {sourceOptions.map((lang) => (
                <option key={lang.code} value={lang.code}>
                  {lang.label}
                </option>
              ))}
            </Select>
          </FormControl>
          <IconButton
            aria-label="Swap languages"
            icon={<FaExchangeAlt />}
            onClick={onSwap}
            isDisabled={disabled || swapDisabled}
            variant="outline"
            size="md"
            colorScheme="orange"
          />
          <FormControl flex={1}>
            <FormLabel
              fontSize="sm"
              fontWeight="semibold"
              className="dview-service-try-option-title"
            >
              Target Language{" "}
              <Text as="span" color="red.500">
                *
              </Text>
            </FormLabel>
            <Select
              value={targetLanguage}
              onChange={(e) => onTargetChange?.(e.target.value)}
              placeholder="Select"
              isDisabled={disabled}
            >
              {targetOptions.map((lang) => (
                <option key={lang.code} value={lang.code}>
                  {lang.label}
                </option>
              ))}
            </Select>
          </FormControl>
        </HStack>
      </VStack>
    );
  }

  return null;
};

export default LanguageConfig;
