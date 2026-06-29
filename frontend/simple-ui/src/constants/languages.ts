// Supported languages and script codes

// Supported languages with script codes
export const SUPPORTED_LANGUAGES = [
  { code: "en", label: "English", scriptCode: "Latn" },
  { code: "hi", label: "Hindi", scriptCode: "Deva" },
  { code: "ta", label: "Tamil", scriptCode: "Taml" },
  { code: "te", label: "Telugu", scriptCode: "Telu" },
  { code: "kn", label: "Kannada", scriptCode: "Knda" },
  { code: "ml", label: "Malayalam", scriptCode: "Mlym" },
  { code: "bn", label: "Bengali", scriptCode: "Beng" },
  { code: "gu", label: "Gujarati", scriptCode: "Gujr" },
  { code: "mr", label: "Marathi", scriptCode: "Deva" },
  { code: "pa", label: "Punjabi", scriptCode: "Guru" },
  { code: "or", label: "Oriya", scriptCode: "Orya" },
  { code: "as", label: "Assamese", scriptCode: "Beng" },
  { code: "ur", label: "Urdu", scriptCode: "Arab" },
  { code: "sa", label: "Sanskrit", scriptCode: "Deva" },
  { code: "ks", label: "Kashmiri", scriptCode: "Arab" },
  { code: "ne", label: "Nepali", scriptCode: "Deva" },
  { code: "sd", label: "Sindhi", scriptCode: "Arab" },
  { code: "kok", label: "Konkani", scriptCode: "Deva" },
  { code: "doi", label: "Dogri", scriptCode: "Deva" },
  { code: "mai", label: "Maithili", scriptCode: "Deva" },
  { code: "brx", label: "Bodo", scriptCode: "Deva" },
  { code: "mni", label: "Manipuri", scriptCode: "Beng" },
  { code: "gom", label: "Goan Konkani", scriptCode: "Latn" },
  { code: "sat", label: "Santali", scriptCode: "Latn" },
  // Custom additions
  // African languages
  { code: "sw", label: "Swahili", scriptCode: "Latn" },
  { code: "yo", label: "Yoruba", scriptCode: "Latn" },
  { code: "ha", label: "Hausa", scriptCode: "Latn" },
  { code: "so", label: "Somali", scriptCode: "Latn" },
  { code: "am", label: "Amharic", scriptCode: "Ethi" },
  { code: "ti", label: "Tigrinya", scriptCode: "Ethi" },
  { code: "ig", label: "Igbo", scriptCode: "Latn" },
  { code: "zu", label: "Zulu", scriptCode: "Latn" },
  { code: "xh", label: "Xhosa", scriptCode: "Latn" },
  { code: "sn", label: "Shona", scriptCode: "Latn" },
  { code: "rw", label: "Kinyarwanda", scriptCode: "Latn" },
  { code: "om", label: "Oromo", scriptCode: "Latn" },
  { code: "lg", label: "Ganda", scriptCode: "Latn" },
  { code: "wo", label: "Wolof", scriptCode: "Latn" },
  { code: "ts", label: "Tsonga", scriptCode: "Latn" },
  { code: "tn", label: "Tswana", scriptCode: "Latn" },
  { code: "af", label: "Afrikaans", scriptCode: "Latn" },
  { code: "fr", label: "French", scriptCode: "Latn" },
  { code: "ar", label: "Arabic", scriptCode: "Arab" },
];

//LLM-supported languages (matching LLM service supported languages)
export const LLM_SUPPORTED_LANGUAGES = [
  { code: "en", label: "English", scriptCode: "Latn" },
  { code: "hi", label: "Hindi", scriptCode: "Deva" },
  { code: "ta", label: "Tamil", scriptCode: "Taml" },
  { code: "te", label: "Telugu", scriptCode: "Telu" },
  { code: "kn", label: "Kannada", scriptCode: "Knda" },
  { code: "ml", label: "Malayalam", scriptCode: "Mlym" },
  { code: "bn", label: "Bengali", scriptCode: "Beng" },
  { code: "gu", label: "Gujarati", scriptCode: "Gujr" },
  { code: "mr", label: "Marathi", scriptCode: "Deva" },
  { code: "pa", label: "Punjabi", scriptCode: "Guru" },
  { code: "or", label: "Oriya", scriptCode: "Orya" },
  { code: "as", label: "Assamese", scriptCode: "Beng" },
  { code: "ur", label: "Urdu", scriptCode: "Arab" },
  { code: "sa", label: "Sanskrit", scriptCode: "Deva" },
  { code: "ks", label: "Kashmiri", scriptCode: "Arab" },
  { code: "ne", label: "Nepali", scriptCode: "Deva" },
  { code: "sd", label: "Sindhi", scriptCode: "Arab" },
  { code: "kok", label: "Konkani", scriptCode: "Deva" },
  { code: "doi", label: "Dogri", scriptCode: "Deva" },
  { code: "mai", label: "Maithili", scriptCode: "Deva" },
  { code: "brx", label: "Bodo", scriptCode: "Deva" },
  { code: "mni", label: "Manipuri", scriptCode: "Beng" },
  { code: "gom", label: "Goan Konkani", scriptCode: "Latn" },
  { code: "sat", label: "Santali", scriptCode: "Latn" },
];

// ASR-supported languages (matching ASR service supported languages)
export const ASR_SUPPORTED_LANGUAGES = [
  { code: "as", label: "Assamese", scriptCode: "Beng" },
  { code: "bn", label: "Bengali", scriptCode: "Beng" },
  { code: "brx", label: "Bodo", scriptCode: "Deva" },
  { code: "doi", label: "Dogri", scriptCode: "Deva" },
  { code: "gu", label: "Gujarati", scriptCode: "Gujr" },
  { code: "hi", label: "Hindi", scriptCode: "Deva" },
  { code: "kn", label: "Kannada", scriptCode: "Knda" },
  { code: "ks", label: "Kashmiri", scriptCode: "Arab" },
  { code: "mai", label: "Maithili", scriptCode: "Deva" },
  { code: "ml", label: "Malayalam", scriptCode: "Mlym" },
  { code: "mni", label: "Manipuri", scriptCode: "Beng" },
  { code: "mr", label: "Marathi", scriptCode: "Deva" },
  { code: "ne", label: "Nepali", scriptCode: "Deva" },
  { code: "or", label: "Odia", scriptCode: "Orya" },
  { code: "pa", label: "Punjabi", scriptCode: "Guru" },
  { code: "sa", label: "Sanskrit", scriptCode: "Deva" },
  { code: "sd", label: "Sindhi", scriptCode: "Arab" },
  { code: "ta", label: "Tamil", scriptCode: "Taml" },
  { code: "te", label: "Telugu", scriptCode: "Telu" },
  { code: "ur", label: "Urdu", scriptCode: "Arab" },
];

// TTS-supported languages (matching TTS service supported languages)
export const TTS_SUPPORTED_LANGUAGES = [
  { code: "hi", label: "Hindi", scriptCode: "Deva" },
  { code: "mr", label: "Marathi", scriptCode: "Deva" },
  { code: "as", label: "Assamese", scriptCode: "Beng" },
  { code: "bn", label: "Bengali", scriptCode: "Beng" },
  { code: "gu", label: "Gujarati", scriptCode: "Gujr" },
  { code: "or", label: "Odia", scriptCode: "Orya" },
  { code: "pa", label: "Punjabi", scriptCode: "Guru" },
];

// Language code to label mapping
export const LANG_CODE_TO_LABEL: { [key: string]: string } =
  SUPPORTED_LANGUAGES.reduce((acc, lang) => {
    acc[lang.code] = lang.label;
    return acc;
  }, {} as { [key: string]: string });

/** Core Indic language codes used by NER, transliteration, and similar services. */
export const INDIC_LANGUAGE_CODES = [
  "en",
  "hi",
  "ta",
  "te",
  "kn",
  "ml",
  "mr",
  "gu",
  "bn",
  "pa",
  "or",
  "as",
] as const;

export type IndicLanguageCode = (typeof INDIC_LANGUAGE_CODES)[number];

/** Language options for Indic-script inference services. */
export const INDIC_LANGUAGE_OPTIONS = INDIC_LANGUAGE_CODES.map((code) => ({
  code,
  label: LANG_CODE_TO_LABEL[code] ?? code,
}));

/** Languages supported in policy configuration UI. */
export const POLICY_LANGUAGE_OPTIONS = ["en", "hi"] as const;
