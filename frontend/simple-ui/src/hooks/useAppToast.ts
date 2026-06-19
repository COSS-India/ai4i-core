import { useCallback } from 'react';
import { type UseToastOptions } from '@chakra-ui/react';
import { showError, type ErrorHandlerService } from '../utils/errorHandler';
import { useToastWithDeduplication } from '../utils/toast';

export function useAppToast() {
  const toast = useToastWithDeduplication();

  const showErrorToast = useCallback(
    (error: unknown, service?: ErrorHandlerService, duration = 7000) => {
      showError(error, { service, duration });
    },
    []
  );

  const showSuccess = useCallback(
    (description: string, title?: string, options?: Partial<UseToastOptions>) => {
      toast({ title, description, status: 'success', ...options });
    },
    [toast]
  );

  const showWarning = useCallback(
    (description: string, title?: string, options?: Partial<UseToastOptions>) => {
      toast({ title, description, status: 'warning', ...options });
    },
    [toast]
  );

  const showInfo = useCallback(
    (description: string, title?: string, options?: Partial<UseToastOptions>) => {
      toast({ title, description, status: 'info', ...options });
    },
    [toast]
  );

  return { toast, showError: showErrorToast, showSuccess, showWarning, showInfo };
}
