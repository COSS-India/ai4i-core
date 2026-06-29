// Service error codes and user-facing messages

/** OCR (Optical Character Recognition) error codes and user-facing messages */
export const OCR_ERRORS = {
  // Upload Errors
  FILE_REQUIRED: {
    title: 'No file selected',
    description: 'Please select an image file to upload.',
    action: 'Select a file',
  },
  INVALID_FORMAT: {
    title: 'File format not supported',
    description: 'File format not supported. Please upload files in JPG or PNG format.',
    action: 'Convert file format',
  },
  FILE_TOO_LARGE: {
    title: 'File size exceeds limit',
    description: 'File size exceeds maximum limit. Please upload a smaller file.',
    action: 'Compress file',
  },
  INVALID_FILE: {
    title: 'File corrupted or invalid',
    description: 'The uploaded file appears to be corrupted or invalid. Please try a different file.',
    action: 'Upload different file',
  },
  UPLOAD_FAILED: {
    title: 'Upload failed',
    description: 'File upload failed. Please check your internet connection and try again.',
    action: 'Retry upload',
  },
  EMPTY_FILE: {
    title: 'Empty file',
    description: 'The uploaded file contains no data. Please upload a valid file.',
    action: 'Upload valid file',
  },
  IMAGE_RESOLUTION_LOW: {
    title: 'Image resolution low',
    description: 'Image resolution is too low for accurate text extraction. Please use a higher quality image.',
    action: 'Upload better quality image',
  },
  // Processing Errors
  LANGUAGE_MISMATCH: {
    title: 'Language mismatch',
    description: 'Image text doesn\'t match the selected language. Please upload an image in the selected language.',
    action: 'Upload matching image',
  },
  NO_TEXT_DETECTED: {
    title: 'No text detected',
    description: 'No text detected in the image. Please ensure the image contains readable text.',
    action: 'Upload image with text',
  },
  TEXT_TOO_BLURRY: {
    title: 'Text too blurry',
    description: 'Text is too blurry to read accurately. Please use a clearer image.',
    action: 'Upload clearer image',
  },
  SERVICE_UNAVAILABLE: {
    title: 'Service unavailable',
    description: 'OCR service is temporarily unavailable. Please try again in a few minutes.',
    action: 'Retry after some time',
  },
  PROCESSING_TIMEOUT: {
    title: 'Processing timeout',
    description: 'Image processing timed out. Please try with a smaller file.',
    action: 'Upload smaller file',
  },
  QUOTA_EXCEEDED: {
    title: 'Quota exceeded',
    description: 'You have exceeded your usage quota for OCR service. Please contact your administrator.',
    action: 'Contact admin or wait',
  },
  RATE_LIMIT_EXCEEDED: {
    title: 'Rate limit exceeded',
    description: 'Too many requests. Please wait before trying again.',
    action: 'Wait and retry',
  },
  MODEL_UNAVAILABLE: {
    title: 'Model unavailable',
    description: 'The selected OCR model is currently unavailable. Please try a different model.',
    action: 'Select different model',
  },
  INVALID_REQUEST: {
    title: 'Invalid request',
    description: 'Invalid request parameters. Please check your input and try again.',
    action: 'Verify input parameters',
  },
} as const;
