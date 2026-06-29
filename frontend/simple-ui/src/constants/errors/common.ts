// Service error codes and user-facing messages

import { NETWORK_ERROR_ENTRY } from "../errorShared";

export const COMMON_ERRORS = {
  NETWORK_ERROR: NETWORK_ERROR_ENTRY,
  INTERNAL_SERVER_ERROR: {
    title: 'Server error',
    description: 'An internal server error occurred. Please try again later or contact support.',
    action: 'Retry or contact support',
  },
  GATEWAY_TIMEOUT: {
    title: 'Gateway timeout',
    description: 'Request timed out. Please try again.',
    action: 'Retry',
  },
  SERVICE_MAINTENANCE: {
    title: 'Service maintenance',
    description: 'Service is under maintenance. Please try again after some time.',
    action: 'Wait and retry',
  },
  INVALID_RESPONSE: {
    title: 'Invalid API response',
    description: 'Received invalid response from server. Please try again.',
    action: 'Retry',
  },
  SESSION_EXPIRED: {
    title: 'Session expired',
    description: 'Your session has expired. Please log in again.',
    action: 'Re-authenticate',
  },
  UNAUTHORIZED: {
    title: 'Unauthorized access',
    description: 'You don\'t have permission to access this service. Please contact your administrator.',
    action: 'Contact admin',
  },
  INVALID_TENANT: {
    title: 'Invalid tenant',
    description: 'Invalid tenant configuration. Please contact support.',
    action: 'Contact support',
  },
  NOT_FOUND: {
    title: 'Resource not found',
    description: 'Requested resource not found. Please verify and try again.',
    action: 'Verify input',
  },
} as const;
