// LLM model identifiers and chat defaults

/** Hardcoded model for POST /api/v1/chat/completions (OpenAI-compatible proxy). */
export const LLM_CHAT_MODEL = "google/gemma-4-E4B-it";

export const AGRINET_MODEL = "agrinet-model";

export const LLM_CHAT_MODELS = [LLM_CHAT_MODEL, AGRINET_MODEL] as const;

export const LLM_CHAT_DEFAULT_SOURCE_LANGUAGE = "en";

export const LLM_CHAT_DEFAULT_TARGET_LANGUAGE = "hi";

export const isLlmChatService = (id?: string): boolean =>
  (LLM_CHAT_MODELS as readonly string[]).includes(id ?? "");
