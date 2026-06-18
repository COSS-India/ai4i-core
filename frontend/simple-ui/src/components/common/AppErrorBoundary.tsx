import React, { Component, type ErrorInfo as ReactErrorInfo, type ReactNode } from 'react';
import { Box, Button, Heading, Text, VStack, Code, useColorModeValue } from '@chakra-ui/react';
import { FiHome, FiRefreshCw, FiRotateCcw } from 'react-icons/fi';

interface AppErrorBoundaryProps {
  children: ReactNode;
  /** Optional fallback when an error is caught. */
  fallback?: ReactNode;
  /** Show a "Go Home" button (defaults to true). */
  showHomeButton?: boolean;
}

interface AppErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: ReactErrorInfo | null;
}

function ErrorFallbackUI({
  error,
  errorInfo,
  onRetry,
  onRefresh,
  onGoHome,
  showHomeButton,
}: {
  error: Error | null;
  errorInfo: ReactErrorInfo | null;
  onRetry: () => void;
  onRefresh: () => void;
  onGoHome: () => void;
  showHomeButton: boolean;
}) {
  const bg = useColorModeValue('white', 'gray.800');
  const borderColor = useColorModeValue('gray.200', 'gray.600');
  const isDev = process.env.NODE_ENV === 'development';

  return (
    <Box
      minH="50vh"
      display="flex"
      alignItems="center"
      justifyContent="center"
      p={6}
    >
      <Box
        maxW="lg"
        w="full"
        bg={bg}
        borderWidth="1px"
        borderColor={borderColor}
        borderRadius="lg"
        p={8}
        boxShadow="md"
      >
        <VStack spacing={4} align="stretch">
          <Heading size="md" color="red.500">
            Something went wrong
          </Heading>
          <Text color="gray.600">
            We hit an unexpected error. You can try again or refresh the page. The rest of the
            application should remain available.
          </Text>
          <VStack spacing={2} align="stretch" pt={2}>
            <Button leftIcon={<FiRotateCcw />} colorScheme="orange" onClick={onRetry}>
              Try Again
            </Button>
            <Button leftIcon={<FiRefreshCw />} variant="outline" onClick={onRefresh}>
              Refresh Page
            </Button>
            {showHomeButton && (
              <Button leftIcon={<FiHome />} variant="ghost" onClick={onGoHome}>
                Go Home
              </Button>
            )}
          </VStack>
          {isDev && error && (
            <Box mt={4} p={3} bg="gray.50" borderRadius="md" overflow="auto" maxH="200px">
              <Text fontSize="sm" fontWeight="semibold" mb={2}>
                Error details (development only)
              </Text>
              <Code display="block" whiteSpace="pre-wrap" fontSize="xs" p={2}>
                {error.message}
                {errorInfo?.componentStack ? `\n${errorInfo.componentStack}` : ''}
              </Code>
            </Box>
          )}
        </VStack>
      </Box>
    </Box>
  );
}

/**
 * Catches React render/runtime errors and displays a friendly fallback UI
 * instead of crashing the entire application.
 */
class AppErrorBoundary extends Component<AppErrorBoundaryProps, AppErrorBoundaryState> {
  constructor(props: AppErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error: Error): Partial<AppErrorBoundaryState> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ReactErrorInfo): void {
    this.setState({ errorInfo });
    if (process.env.NODE_ENV === 'development') {
      console.error('[AppErrorBoundary]', error, errorInfo);
    }
  }

  handleRetry = (): void => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  handleRefresh = (): void => {
    if (typeof window !== 'undefined') {
      window.location.reload();
    }
  };

  handleGoHome = (): void => {
    if (typeof window !== 'undefined') {
      window.location.href = '/';
    }
  };

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <ErrorFallbackUI
          error={this.state.error}
          errorInfo={this.state.errorInfo}
          onRetry={this.handleRetry}
          onRefresh={this.handleRefresh}
          onGoHome={this.handleGoHome}
          showHomeButton={this.props.showHomeButton ?? true}
        />
      );
    }

    return this.props.children;
  }
}

export default AppErrorBoundary;
