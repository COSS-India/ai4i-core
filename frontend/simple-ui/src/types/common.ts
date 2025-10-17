// Common TypeScript type definitions shared across all services

// Language Types
export interface Language {
  code: string;
  label: string;
  scriptCode?: string;
}

export interface LanguagePair {
  sourceLanguage: string;
  targetLanguage: string;
  sourceScriptCode?: string;
  targetScriptCode?: string;
}

// Service Types
export type ServiceType = 'asr' | 'tts' | 'nmt';
export type ServiceStatus = 'healthy' | 'unhealthy' | 'unknown';
export type InferenceMode = 'rest' | 'streaming';

// API Response Types
export interface ApiResponse<T> {
  data: T;
  status: number;
  headers: Record<string, string>;
}

export interface ErrorResponse {
  detail: {
    message: string;
    code: string;
    timestamp: number;
  };
}

// Stats Types
export interface RequestStats {
  wordCount: number;
  responseTime: number;
  timestamp: number;
}

export interface AudioStats {
  duration: number;
  sampleRate: number;
  format: string;
}

// Audio Types
export type AudioFormat = 'wav' | 'mp3' | 'flac' | 'ogg' | 'pcm';
export type Gender = 'male' | 'female';
export type SampleRate = 8000 | 16000 | 22050 | 44100 | 48000;

// WebSocket Types
export type SocketStatus = 'connected' | 'disconnected' | 'connecting' | 'error';

export interface StreamingConfig {
  serviceId: string;
  language: string;
  samplingRate: number;
  apiKey?: string;
}

// UI Component Types
export interface BaseComponentProps {
  className?: string;
  children?: React.ReactNode;
}

export interface LoadingState {
  isLoading: boolean;
  error?: string | null;
}

export interface PaginationProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

// Form Types
export interface FormFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  error?: string;
  required?: boolean;
  disabled?: boolean;
}

// Theme Types
export interface ThemeColors {
  primary: string;
  secondary: string;
  accent: string;
  background: string;
  surface: string;
  text: string;
  textSecondary: string;
  border: string;
  error: string;
  warning: string;
  success: string;
  info: string;
}

// Navigation Types
export interface NavItem {
  id: string;
  label: string;
  path: string;
  icon?: React.ComponentType;
  children?: NavItem[];
}

// API Configuration Types
export interface ApiConfig {
  baseURL: string;
  timeout: number;
  headers: Record<string, string>;
}

// File Upload Types
export interface FileUploadProps {
  accept?: string;
  multiple?: boolean;
  maxSize?: number;
  onFileSelect: (files: File[]) => void;
  onError?: (error: string) => void;
}

// Toast/Notification Types
export interface ToastProps {
  title: string;
  description?: string;
  status: 'success' | 'error' | 'warning' | 'info';
  duration?: number;
  isClosable?: boolean;
}

// Modal Types
export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  size?: 'sm' | 'md' | 'lg' | 'xl' | 'full';
  children: React.ReactNode;
}

// Table Types
export interface TableColumn<T> {
  key: keyof T;
  label: string;
  sortable?: boolean;
  render?: (value: any, item: T) => React.ReactNode;
}

export interface TableProps<T> {
  data: T[];
  columns: TableColumn<T>[];
  loading?: boolean;
  onSort?: (key: keyof T, direction: 'asc' | 'desc') => void;
  onRowClick?: (item: T) => void;
}