// Voice selector component for TTS with gender, format, and sample rate options

import {
  FormControl,
  FormLabel,
  Select,
  Spinner,
  Stack,
  Text,
  useMediaQuery,
} from "@chakra-ui/react";
import React from "react";
import {
  AUDIO_FORMATS,
  GENDER_OPTIONS,
  LANG_CODE_TO_LABEL,
} from "../../config/constants";
import { VoiceSelectorProps } from "../../types/tts";

const VoiceSelector: React.FC<VoiceSelectorProps> = ({
  language,
  gender,
  audioFormat,
  samplingRate,
  onLanguageChange,
  onGenderChange,
  onFormatChange,
  onSampleRateChange,
  availableLanguages,
  availableVoices,
  loading = false,
}) => {
  const [isMobile] = useMediaQuery("(max-width: 768px)");

  const handleLanguageChange = (
    event: React.ChangeEvent<HTMLSelectElement>
  ) => {
    onLanguageChange(event.target.value);
  };

  const handleGenderChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    onGenderChange(event.target.value as "male" | "female");
  };

  const handleFormatChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    onFormatChange(event.target.value as any);
  };

  // Sampling rate selection removed from UI

  if (loading) {
    return (
      <Stack spacing={4} align="center" py={8}>
        <Spinner size="lg" color="orange.500" />
        <Text color="gray.600">Loading voice options...</Text>
      </Stack>
    );
  }

  // Sort options alphabetically by display label
  const sortedLanguages = [...availableLanguages].sort((a, b) =>
    (LANG_CODE_TO_LABEL[a] || a).localeCompare(LANG_CODE_TO_LABEL[b] || b)
  );
  const sortedGenders = [...GENDER_OPTIONS].sort((a, b) =>
    a.label.localeCompare(b.label)
  );
  const sortedFormats = [...AUDIO_FORMATS].sort((a, b) =>
    a.localeCompare(b)
  );

  return (
    <Stack spacing={4} direction={isMobile ? "column" : "row"}>
      {/* Language Selection */}
      <FormControl flex={1}>
        <FormLabel className="dview-service-try-option-title">
          Language{" "}
          <Text as="span" color="red.500">*</Text>
        </FormLabel>
        <Select
          value={language}
          onChange={handleLanguageChange}
          placeholder="Select"
          disabled={availableLanguages.length === 0}
        >
          {sortedLanguages.map((lang) => (
            <option key={lang} value={lang}>
              {LANG_CODE_TO_LABEL[lang] || lang}
            </option>
          ))}
        </Select>
      </FormControl>

      {/* Voice Selection */}
      <FormControl flex={1}>
        <FormLabel className="dview-service-try-option-title">
          Voice{" "}
          <Text as="span" color="red.500">*</Text>
        </FormLabel>
        <Select
          value={gender}
          onChange={handleGenderChange}
          placeholder="Select"
        >
          {sortedGenders.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
      </FormControl>

      {/* Audio Format Selection */}
      <FormControl flex={1}>
        <FormLabel className="dview-service-try-option-title">
          Audio Format{" "}
          <Text as="span" color="red.500">*</Text>
        </FormLabel>
        <Select
          value={audioFormat}
          onChange={handleFormatChange}
          placeholder="Select"
        >
          {sortedFormats.map((format) => (
            <option key={format} value={format}>
              {format.toUpperCase()}
            </option>
          ))}
        </Select>
      </FormControl>

      {/* Sampling Rate control removed per requirements */}
    </Stack>
  );
};

export default VoiceSelector;
