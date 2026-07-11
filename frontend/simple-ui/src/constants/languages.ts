// Supported languages and script codes

export type LanguageDef = {
  code: string;
  label: string;
  scriptCode: string;
};

const LANGUAGE_BY_CODE = {
  en: { code: "en", label: "English", scriptCode: "Latn" },
  hi: { code: "hi", label: "Hindi", scriptCode: "Deva" },
  ta: { code: "ta", label: "Tamil", scriptCode: "Taml" },
  te: { code: "te", label: "Telugu", scriptCode: "Telu" },
  kn: { code: "kn", label: "Kannada", scriptCode: "Knda" },
  ml: { code: "ml", label: "Malayalam", scriptCode: "Mlym" },
  bn: { code: "bn", label: "Bengali", scriptCode: "Beng" },
  gu: { code: "gu", label: "Gujarati", scriptCode: "Gujr" },
  mr: { code: "mr", label: "Marathi", scriptCode: "Deva" },
  pa: { code: "pa", label: "Punjabi", scriptCode: "Guru" },
  or: { code: "or", label: "Oriya", scriptCode: "Orya" },
  as: { code: "as", label: "Assamese", scriptCode: "Beng" },
  ur: { code: "ur", label: "Urdu", scriptCode: "Arab" },
  sa: { code: "sa", label: "Sanskrit", scriptCode: "Deva" },
  ks: { code: "ks", label: "Kashmiri", scriptCode: "Arab" },
  ne: { code: "ne", label: "Nepali", scriptCode: "Deva" },
  sd: { code: "sd", label: "Sindhi", scriptCode: "Arab" },
  kok: { code: "kok", label: "Konkani", scriptCode: "Deva" },
  doi: { code: "doi", label: "Dogri", scriptCode: "Deva" },
  mai: { code: "mai", label: "Maithili", scriptCode: "Deva" },
  brx: { code: "brx", label: "Bodo", scriptCode: "Deva" },
  mni: { code: "mni", label: "Manipuri", scriptCode: "Beng" },
  gom: { code: "gom", label: "Goan Konkani", scriptCode: "Latn" },
  sat: { code: "sat", label: "Santali", scriptCode: "Latn" },
  sw: { code: "sw", label: "Swahili", scriptCode: "Latn" },
  yo: { code: "yo", label: "Yoruba", scriptCode: "Latn" },
  ha: { code: "ha", label: "Hausa", scriptCode: "Latn" },
  so: { code: "so", label: "Somali", scriptCode: "Latn" },
  am: { code: "am", label: "Amharic", scriptCode: "Ethi" },
  ti: { code: "ti", label: "Tigrinya", scriptCode: "Ethi" },
  ig: { code: "ig", label: "Igbo", scriptCode: "Latn" },
  zu: { code: "zu", label: "Zulu", scriptCode: "Latn" },
  xh: { code: "xh", label: "Xhosa", scriptCode: "Latn" },
  sn: { code: "sn", label: "Shona", scriptCode: "Latn" },
  rw: { code: "rw", label: "Kinyarwanda", scriptCode: "Latn" },
  om: { code: "om", label: "Oromo", scriptCode: "Latn" },
  lg: { code: "lg", label: "Ganda", scriptCode: "Latn" },
  wo: { code: "wo", label: "Wolof", scriptCode: "Latn" },
  ts: { code: "ts", label: "Tsonga", scriptCode: "Latn" },
  tn: { code: "tn", label: "Tswana", scriptCode: "Latn" },
  af: { code: "af", label: "Afrikaans", scriptCode: "Latn" },
  fr: { code: "fr", label: "French", scriptCode: "Latn" },
  ar: { code: "ar", label: "Arabic", scriptCode: "Arab" },
} as const satisfies Record<string, LanguageDef>;

const LLM_LANGUAGE_CODES = [
  "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa", "or", "as", "ur", "sa", "ks", "ne",
  "sd", "kok", "doi", "mai", "brx", "mni", "gom", "sat",
] as const;

const AFRICAN_LANGUAGE_CODES = [
  "sw", "yo", "ha", "so", "am", "ti", "ig", "zu", "xh", "sn", "rw", "om", "lg", "wo", "ts", "tn",
  "af", "fr", "ar",
] as const;

const ASR_LANGUAGE_CODES = [
  "as", "bn", "brx", "doi", "gu", "hi", "kn", "ks", "mai", "ml", "mni", "mr", "ne", "or", "pa",
  "sa", "sd", "ta", "te", "ur",
] as const;

const TTS_LANGUAGE_CODES = ["hi", "mr", "as", "bn", "gu", "or", "pa"] as const;

const ODIA_LABEL = "Odia";

function languagesFromCodes(
  codes: readonly string[],
  labelOverrides?: Partial<Record<string, string>>,
): LanguageDef[] {
  return codes.map((code) => {
    const base = LANGUAGE_BY_CODE[code as keyof typeof LANGUAGE_BY_CODE];
    const label = labelOverrides?.[code];
    return label ? { ...base, label } : { ...base };
  });
}

/** All languages in the UI catalog (Indic + African). */
export const SUPPORTED_LANGUAGES = languagesFromCodes([
  ...LLM_LANGUAGE_CODES,
  ...AFRICAN_LANGUAGE_CODES,
]);

/** LLM-supported languages (matching LLM service supported languages). */
export const LLM_SUPPORTED_LANGUAGES = languagesFromCodes(LLM_LANGUAGE_CODES);

/** ASR-supported languages (matching ASR service supported languages). */
export const ASR_SUPPORTED_LANGUAGES = languagesFromCodes(ASR_LANGUAGE_CODES, {
  or: ODIA_LABEL,
});

/** TTS-supported languages (matching TTS service supported languages). */
export const TTS_SUPPORTED_LANGUAGES = languagesFromCodes(TTS_LANGUAGE_CODES, {
  or: ODIA_LABEL,
});

export const LANG_CODE_TO_LABEL: Record<string, string> = Object.fromEntries(
  SUPPORTED_LANGUAGES.map((lang) => [lang.code, lang.label]),
);

/** Core Indic language codes used by NER, transliteration, and similar services. */
export const INDIC_LANGUAGE_CODES = [
  "en", "hi", "ta", "te", "kn", "ml", "mr", "gu", "bn", "pa", "or", "as",
] as const;

export type IndicLanguageCode = (typeof INDIC_LANGUAGE_CODES)[number];

/** Language options for Indic-script inference services. */
export const INDIC_LANGUAGE_OPTIONS = INDIC_LANGUAGE_CODES.map((code) => ({
  code,
  label: LANG_CODE_TO_LABEL[code] ?? code,
}));

/** Languages supported in policy configuration UI. */
export const POLICY_LANGUAGE_OPTIONS = ["en", "hi"] as const;
