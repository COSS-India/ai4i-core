// Shared types for reusable AI service page components

import type { ReactNode } from "react";

/** Input modality rendered in the request panel */
export type ServiceInputType = "text" | "audio" | "image" | "custom";

/** How language controls are shown */
export type LanguageConfigMode =
  | "none"
  | "source-only"
  | "source-target"
  | "language-pair";

export interface ServiceOption {
  id: string;
  label: string;
  description?: string;
  version?: string;
}

export interface LanguageOption {
  code: string;
  label: string;
}

export interface LanguagePairOption {
  sourceLanguage: string;
  targetLanguage: string;
  sourceScriptCode?: string;
  targetScriptCode?: string;
}

export interface ResponseMetadataItem {
  label: string;
  value: string | number;
  helpText?: string;
}

export type ResponseActionKind = "copy" | "download" | "export" | "custom";

export interface ResponseActionConfig {
  id: string;
  label: string;
  kind?: ResponseActionKind;
  onClick: () => void;
  /** When false, action is hidden (e.g. export only for some services) */
  visible?: boolean;
}

export interface ServiceDropdownProps {
  label?: string;
  required?: boolean;
  value: string;
  onChange: (serviceId: string) => void;
  options: ServiceOption[];
  loading?: boolean;
  disabled?: boolean;
  placeholder?: string;
  error?: string | null;
  /** Show name/description box for the selected service */
  showSelectedDetails?: boolean;
}

export interface LanguageConfigProps {
  mode: LanguageConfigMode;
  loading?: boolean;
  disabled?: boolean;
  /** source-only or source-target */
  sourceLanguage?: string;
  targetLanguage?: string;
  onSourceChange?: (code: string) => void;
  onTargetChange?: (code: string) => void;
  sourceOptions?: LanguageOption[];
  targetOptions?: LanguageOption[];
  onSwap?: () => void;
  swapDisabled?: boolean;
  /** language-pair mode */
  languagePair?: LanguagePairOption;
  onLanguagePairChange?: (pair: LanguagePairOption) => void;
  languagePairOptions?: LanguagePairOption[];
  getLanguagePairLabel?: (pair: LanguagePairOption) => string;
}

export interface ServiceTextInputProps {
  value: string;
  onChange: (value: string) => void;
  label?: string;
  placeholder?: string;
  maxLength?: number;
  disabled?: boolean;
  required?: boolean;
  rows?: number;
  /** Show character counter below the field (default true) */
  showCharCounter?: boolean;
  resize?: "vertical" | "horizontal" | "none" | "both";
}

export interface ServiceAudioInputProps {
  /** Base64 audio payload (recording or upload) */
  value: string | null;
  onChange: (audioBase64: string | null) => void;
  label?: string;
  required?: boolean;
  helperSlot?: ReactNode;
  disabled?: boolean;
  sampleRate?: number;
  /** Show microphone record UI (default true) */
  showRecording?: boolean;
  /** Show file upload UI (default true) */
  showUpload?: boolean;
  readyMessage?: string;
  showSuccessAlert?: boolean;
  /**
   * Increment to reset recorder/upload UI after parent clears audio.
   */
  clearToken?: number;
  /** Called when user clears audio (in addition to onChange(null)) */
  onClear?: () => void;
  /**
   * External recording state (e.g. useASR). When omitted, AudioInput uses useAudioRecorder internally.
   */
  isRecording?: boolean;
  onRecordingChange?: (recording: boolean) => void;
  timer?: number;
  /**
   * @deprecated Use value/onChange props instead of children.
   */
  children?: ReactNode;
}

export interface ServiceImageInputProps {
  file: File | null;
  onFileChange: (file: File | null) => void;
  previewUrl?: string | null;
  label?: string;
  required?: boolean;
  disabled?: boolean;
  maxSizeBytes?: number;
  acceptedFormats?: string;
  formatHint?: string;
}

export interface SubmitButtonProps {
  label: string;
  loadingLabel?: string;
  onClick: () => void;
  isLoading?: boolean;
  isDisabled?: boolean;
  icon?: ReactNode;
}

export interface RequestContainerProps {
  serviceDropdown?: ServiceDropdownProps;
  languageConfig?: LanguageConfigProps;
  inputType?: ServiceInputType;
  textInput?: ServiceTextInputProps;
  audioInput?: ServiceAudioInputProps;
  imageInput?: ServiceImageInputProps;
  /** Custom input when inputType is "custom" */
  customInput?: ReactNode;
  helperText?: ReactNode;
  helperItems?: string[];
  submitButton: SubmitButtonProps;
  /** Extra controls (e.g. inference mode, voice selector) */
  children?: ReactNode;
  topSlot?: ReactNode;
  spacing?: number;
}

export interface ResponseContainerProps {
  fetching?: boolean;
  fetchingLabel?: string;
  error?: string | null;
  fetched?: boolean;
  hasResult?: boolean;
  resultTitle?: string;
  resultContent?: string;
  /** Fully custom result UI (overrides resultTitle/resultContent when set) */
  result?: ReactNode;
  metadata?: ResponseMetadataItem[];
  actions?: ResponseActionConfig[];
  onClear?: () => void;
  clearLabel?: string;
  children?: ReactNode;
}

export interface ServicePageLayoutProps {
  serviceId: string;
  pageTitle?: string;
  pageDescription?: string;
  headTitle?: string;
  headDescription?: string;
  headingSize?: "xl" | "lg";
  /** Optional control shown to the right of the page title (e.g. pipeline builder link) */
  headerExtra?: ReactNode;
  banner?: ReactNode;
  requestPanel: ReactNode;
  responsePanel: ReactNode;
  maxWidth?: string;
}
