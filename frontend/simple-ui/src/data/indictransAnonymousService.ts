/**
 * Hardcoded IndicTrans service for anonymous (try-it) NMT users.
 * Same format as the service-type API response used in NMT for showing languages.
 */
export const INDICTRANS_ANONYMOUS_SERVICE_ID = "ai4bharat/indictrans--gpu-t4";

export interface IndicTransLanguagePair {
  sourceLanguage: string;
  targetLanguage: string;
  sourceScriptCode: string;
  targetScriptCode: string;
}

/** Service response shape matching the API (service type) used in NMT */
export interface IndicTransServiceResponse {
  serviceId: string;
  name: string;
  serviceDescription: string;
  task: { type: string };
  languages: IndicTransLanguagePair[];
}

/** Hardcoded IndicTrans-v2 service in API response format */
export const INDICTRANS_ANONYMOUS_SERVICE: IndicTransServiceResponse = {
  serviceId: INDICTRANS_ANONYMOUS_SERVICE_ID,
  name: "IndicTrans-v2 All Directions on T4",
  serviceDescription: "IndicTrans NMT models hosted by AI4Bharat models.",
  task: { type: "nmt" },
  languages: [
    { sourceLanguage: "en", targetLanguage: "as", sourceScriptCode: "Latn", targetScriptCode: "Beng" },
    { sourceLanguage: "en", targetLanguage: "bn", sourceScriptCode: "Latn", targetScriptCode: "Beng" },
    { sourceLanguage: "en", targetLanguage: "brx", sourceScriptCode: "Latn", targetScriptCode: "Deva" },
    { sourceLanguage: "en", targetLanguage: "doi", sourceScriptCode: "Latn", targetScriptCode: "Deva" },
    { sourceLanguage: "en", targetLanguage: "gom", sourceScriptCode: "Latn", targetScriptCode: "Deva" },
    { sourceLanguage: "en", targetLanguage: "gu", sourceScriptCode: "Latn", targetScriptCode: "Gujr" },
    { sourceLanguage: "en", targetLanguage: "hi", sourceScriptCode: "Latn", targetScriptCode: "Deva" },
    { sourceLanguage: "en", targetLanguage: "kn", sourceScriptCode: "Latn", targetScriptCode: "Knda" },
    { sourceLanguage: "en", targetLanguage: "ks", sourceScriptCode: "Latn", targetScriptCode: "Aran" },
    { sourceLanguage: "en", targetLanguage: "ks", sourceScriptCode: "Latn", targetScriptCode: "Deva" },
    { sourceLanguage: "en", targetLanguage: "mai", sourceScriptCode: "Latn", targetScriptCode: "Deva" },
    { sourceLanguage: "en", targetLanguage: "ml", sourceScriptCode: "Latn", targetScriptCode: "Mlym" },
    { sourceLanguage: "en", targetLanguage: "mni", sourceScriptCode: "Latn", targetScriptCode: "Mtei" },
    { sourceLanguage: "en", targetLanguage: "mni", sourceScriptCode: "Latn", targetScriptCode: "Beng" },
    { sourceLanguage: "en", targetLanguage: "mr", sourceScriptCode: "Latn", targetScriptCode: "Deva" },
    { sourceLanguage: "en", targetLanguage: "ne", sourceScriptCode: "Latn", targetScriptCode: "Deva" },
    { sourceLanguage: "en", targetLanguage: "or", sourceScriptCode: "Latn", targetScriptCode: "Orya" },
    { sourceLanguage: "en", targetLanguage: "pa", sourceScriptCode: "Latn", targetScriptCode: "Guru" },
    { sourceLanguage: "en", targetLanguage: "sa", sourceScriptCode: "Latn", targetScriptCode: "Deva" },
    { sourceLanguage: "en", targetLanguage: "sat", sourceScriptCode: "Latn", targetScriptCode: "Olck" },
    { sourceLanguage: "en", targetLanguage: "sd", sourceScriptCode: "Latn", targetScriptCode: "Arab" },
    { sourceLanguage: "en", targetLanguage: "sd", sourceScriptCode: "Latn", targetScriptCode: "Deva" },
    { sourceLanguage: "en", targetLanguage: "ta", sourceScriptCode: "Latn", targetScriptCode: "Taml" },
    { sourceLanguage: "en", targetLanguage: "te", sourceScriptCode: "Latn", targetScriptCode: "Telu" },
    { sourceLanguage: "en", targetLanguage: "ur", sourceScriptCode: "Latn", targetScriptCode: "Aran" },
    { sourceLanguage: "as", targetLanguage: "en", sourceScriptCode: "Beng", targetScriptCode: "Latn" },
    { sourceLanguage: "bn", targetLanguage: "en", sourceScriptCode: "Beng", targetScriptCode: "Latn" },
    { sourceLanguage: "brx", targetLanguage: "en", sourceScriptCode: "Deva", targetScriptCode: "Latn" },
    { sourceLanguage: "doi", targetLanguage: "en", sourceScriptCode: "Deva", targetScriptCode: "Latn" },
    { sourceLanguage: "gom", targetLanguage: "en", sourceScriptCode: "Deva", targetScriptCode: "Latn" },
    { sourceLanguage: "gu", targetLanguage: "en", sourceScriptCode: "Gujr", targetScriptCode: "Latn" },
    { sourceLanguage: "hi", targetLanguage: "en", sourceScriptCode: "Deva", targetScriptCode: "Latn" },
    { sourceLanguage: "kn", targetLanguage: "en", sourceScriptCode: "Knda", targetScriptCode: "Latn" },
    { sourceLanguage: "ks", targetLanguage: "en", sourceScriptCode: "Aran", targetScriptCode: "Latn" },
    { sourceLanguage: "ks", targetLanguage: "en", sourceScriptCode: "Deva", targetScriptCode: "Latn" },
    { sourceLanguage: "mai", targetLanguage: "en", sourceScriptCode: "Deva", targetScriptCode: "Latn" },
    { sourceLanguage: "ml", targetLanguage: "en", sourceScriptCode: "Mlym", targetScriptCode: "Latn" },
    { sourceLanguage: "mni", targetLanguage: "en", sourceScriptCode: "Mtei", targetScriptCode: "Latn" },
    { sourceLanguage: "mni", targetLanguage: "en", sourceScriptCode: "Beng", targetScriptCode: "Latn" },
    { sourceLanguage: "mr", targetLanguage: "en", sourceScriptCode: "Deva", targetScriptCode: "Latn" },
    { sourceLanguage: "ne", targetLanguage: "en", sourceScriptCode: "Deva", targetScriptCode: "Latn" },
    { sourceLanguage: "or", targetLanguage: "en", sourceScriptCode: "Orya", targetScriptCode: "Latn" },
    { sourceLanguage: "pa", targetLanguage: "en", sourceScriptCode: "Guru", targetScriptCode: "Latn" },
    { sourceLanguage: "sa", targetLanguage: "en", sourceScriptCode: "Deva", targetScriptCode: "Latn" },
    { sourceLanguage: "sat", targetLanguage: "en", sourceScriptCode: "Olck", targetScriptCode: "Latn" },
    { sourceLanguage: "sd", targetLanguage: "en", sourceScriptCode: "Arab", targetScriptCode: "Latn" },
    { sourceLanguage: "sd", targetLanguage: "en", sourceScriptCode: "Deva", targetScriptCode: "Latn" },
    { sourceLanguage: "ta", targetLanguage: "en", sourceScriptCode: "Taml", targetScriptCode: "Latn" },
    { sourceLanguage: "te", targetLanguage: "en", sourceScriptCode: "Telu", targetScriptCode: "Latn" },
    { sourceLanguage: "ur", targetLanguage: "en", sourceScriptCode: "Aran", targetScriptCode: "Latn" },
    { sourceLanguage: "as", targetLanguage: "bn", sourceScriptCode: "Beng", targetScriptCode: "Beng" },
    { sourceLanguage: "as", targetLanguage: "hi", sourceScriptCode: "Beng", targetScriptCode: "Deva" },
    { sourceLanguage: "as", targetLanguage: "ta", sourceScriptCode: "Beng", targetScriptCode: "Taml" },
    { sourceLanguage: "as", targetLanguage: "te", sourceScriptCode: "Beng", targetScriptCode: "Telu" },
    { sourceLanguage: "bn", targetLanguage: "as", sourceScriptCode: "Beng", targetScriptCode: "Beng" },
    { sourceLanguage: "bn", targetLanguage: "hi", sourceScriptCode: "Beng", targetScriptCode: "Deva" },
    { sourceLanguage: "bn", targetLanguage: "ta", sourceScriptCode: "Beng", targetScriptCode: "Taml" },
    { sourceLanguage: "bn", targetLanguage: "te", sourceScriptCode: "Beng", targetScriptCode: "Telu" },
    { sourceLanguage: "hi", targetLanguage: "as", sourceScriptCode: "Deva", targetScriptCode: "Beng" },
    { sourceLanguage: "hi", targetLanguage: "bn", sourceScriptCode: "Deva", targetScriptCode: "Beng" },
    { sourceLanguage: "hi", targetLanguage: "ta", sourceScriptCode: "Deva", targetScriptCode: "Taml" },
    { sourceLanguage: "hi", targetLanguage: "te", sourceScriptCode: "Deva", targetScriptCode: "Telu" },
    { sourceLanguage: "ta", targetLanguage: "as", sourceScriptCode: "Taml", targetScriptCode: "Beng" },
    { sourceLanguage: "ta", targetLanguage: "bn", sourceScriptCode: "Taml", targetScriptCode: "Beng" },
    { sourceLanguage: "ta", targetLanguage: "hi", sourceScriptCode: "Taml", targetScriptCode: "Deva" },
    { sourceLanguage: "ta", targetLanguage: "te", sourceScriptCode: "Taml", targetScriptCode: "Telu" },
    { sourceLanguage: "te", targetLanguage: "as", sourceScriptCode: "Telu", targetScriptCode: "Beng" },
    { sourceLanguage: "te", targetLanguage: "bn", sourceScriptCode: "Telu", targetScriptCode: "Beng" },
    { sourceLanguage: "te", targetLanguage: "hi", sourceScriptCode: "Telu", targetScriptCode: "Deva" },
    { sourceLanguage: "te", targetLanguage: "ta", sourceScriptCode: "Telu", targetScriptCode: "Taml" },
    { sourceLanguage: "brx", targetLanguage: "hi", sourceScriptCode: "Deva", targetScriptCode: "Deva" },
    { sourceLanguage: "doi", targetLanguage: "hi", sourceScriptCode: "Deva", targetScriptCode: "Deva" },
    { sourceLanguage: "gom", targetLanguage: "hi", sourceScriptCode: "Deva", targetScriptCode: "Deva" },
    { sourceLanguage: "gu", targetLanguage: "hi", sourceScriptCode: "Gujr", targetScriptCode: "Deva" },
    { sourceLanguage: "hi", targetLanguage: "brx", sourceScriptCode: "Deva", targetScriptCode: "Deva" },
    { sourceLanguage: "hi", targetLanguage: "doi", sourceScriptCode: "Deva", targetScriptCode: "Deva" },
    { sourceLanguage: "hi", targetLanguage: "gom", sourceScriptCode: "Deva", targetScriptCode: "Deva" },
    { sourceLanguage: "hi", targetLanguage: "gu", sourceScriptCode: "Deva", targetScriptCode: "Gujr" },
    { sourceLanguage: "hi", targetLanguage: "kn", sourceScriptCode: "Deva", targetScriptCode: "Knda" },
    { sourceLanguage: "hi", targetLanguage: "ks", sourceScriptCode: "Deva", targetScriptCode: "Aran" },
    { sourceLanguage: "hi", targetLanguage: "ks", sourceScriptCode: "Deva", targetScriptCode: "Deva" },
    { sourceLanguage: "hi", targetLanguage: "mai", sourceScriptCode: "Deva", targetScriptCode: "Deva" },
    { sourceLanguage: "hi", targetLanguage: "ml", sourceScriptCode: "Deva", targetScriptCode: "Mlym" },
    { sourceLanguage: "hi", targetLanguage: "mni", sourceScriptCode: "Deva", targetScriptCode: "Mtei" },
    { sourceLanguage: "hi", targetLanguage: "mni", sourceScriptCode: "Deva", targetScriptCode: "Beng" },
    { sourceLanguage: "hi", targetLanguage: "mr", sourceScriptCode: "Deva", targetScriptCode: "Deva" },
    { sourceLanguage: "hi", targetLanguage: "ne", sourceScriptCode: "Deva", targetScriptCode: "Deva" },
    { sourceLanguage: "hi", targetLanguage: "or", sourceScriptCode: "Deva", targetScriptCode: "Orya" },
    { sourceLanguage: "hi", targetLanguage: "pa", sourceScriptCode: "Deva", targetScriptCode: "Guru" },
    { sourceLanguage: "hi", targetLanguage: "sa", sourceScriptCode: "Deva", targetScriptCode: "Deva" },
    { sourceLanguage: "hi", targetLanguage: "sat", sourceScriptCode: "Deva", targetScriptCode: "Olck" },
    { sourceLanguage: "hi", targetLanguage: "sd", sourceScriptCode: "Deva", targetScriptCode: "Arab" },
    { sourceLanguage: "hi", targetLanguage: "sd", sourceScriptCode: "Deva", targetScriptCode: "Deva" },
    { sourceLanguage: "hi", targetLanguage: "ur", sourceScriptCode: "Deva", targetScriptCode: "Aran" },
    { sourceLanguage: "kn", targetLanguage: "hi", sourceScriptCode: "Knda", targetScriptCode: "Deva" },
    { sourceLanguage: "ml", targetLanguage: "hi", sourceScriptCode: "Mlym", targetScriptCode: "Deva" },
    { sourceLanguage: "mr", targetLanguage: "hi", sourceScriptCode: "Deva", targetScriptCode: "Deva" },
    { sourceLanguage: "ne", targetLanguage: "hi", sourceScriptCode: "Deva", targetScriptCode: "Deva" },
    { sourceLanguage: "or", targetLanguage: "hi", sourceScriptCode: "Orya", targetScriptCode: "Deva" },
    { sourceLanguage: "pa", targetLanguage: "hi", sourceScriptCode: "Guru", targetScriptCode: "Deva" },
    { sourceLanguage: "sa", targetLanguage: "hi", sourceScriptCode: "Deva", targetScriptCode: "Deva" },
    { sourceLanguage: "ur", targetLanguage: "hi", sourceScriptCode: "Aran", targetScriptCode: "Deva" },
  ],
};
