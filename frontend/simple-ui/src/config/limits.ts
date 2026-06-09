// Shared input and file size limits

// Maximum text length
export const MAX_TEXT_LENGTH = 512;

/** Guest users may make this many inference requests per service per hour. */
export const GUEST_REQUESTS_PER_HOUR_PER_SERVICE = 10;

// Minimum recording duration in seconds
export const MIN_RECORDING_DURATION = 1;

// Maximum recording duration in seconds
export const MAX_RECORDING_DURATION = 60;

// Maximum file size for audio uploads (10MB)
export const MAX_AUDIO_FILE_SIZE = 10 * 1024 * 1024; // 10MB

// Maximum file size for image uploads (10MB)
export const MAX_IMAGE_FILE_SIZE = 10 * 1024 * 1024; // 10MB
