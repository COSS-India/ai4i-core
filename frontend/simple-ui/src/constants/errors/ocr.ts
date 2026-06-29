// Service error codes and user-facing messages

import {
  SHARED_SERVICE_ERRORS,
  quotaExceeded,
  serviceUnavailable,
} from "../errorShared";
import { UPLOAD_ERRORS } from "./upload";

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
  FILE_TOO_LARGE: UPLOAD_ERRORS.FILE_TOO_LARGE,
  INVALID_FILE: UPLOAD_ERRORS.INVALID_FILE,
  UPLOAD_FAILED: UPLOAD_ERRORS.UPLOAD_FAILED,
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
  SERVICE_UNAVAILABLE: serviceUnavailable('OCR service'),
  PROCESSING_TIMEOUT: {
    title: 'Processing timeout',
    description: 'Image processing timed out. Please try with a smaller file.',
    action: 'Upload smaller file',
  },
  QUOTA_EXCEEDED: quotaExceeded('OCR service'),
  RATE_LIMIT_EXCEEDED: SHARED_SERVICE_ERRORS.RATE_LIMIT_EXCEEDED,
  MODEL_UNAVAILABLE: {
    title: 'Model unavailable',
    description: 'The selected OCR model is currently unavailable. Please try a different model.',
    action: 'Select different model',
  },
  INVALID_REQUEST: SHARED_SERVICE_ERRORS.INVALID_REQUEST,
} as const;
