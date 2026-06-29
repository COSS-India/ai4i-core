import { Alert, AlertDescription, AlertIcon, Center, Spinner, Text, VStack } from "@chakra-ui/react";
import React from "react";
import { METERING } from "../../constants";

interface MeteringAlertsProps {
  errorMessage?: string | null;
  isDegraded?: boolean;
}

/** Dashboard-level error and degraded-data banners. */
export const MeteringAlerts: React.FC<MeteringAlertsProps> = ({
  errorMessage,
  isDegraded = false,
}) => {
  if (!errorMessage && !isDegraded) return null;

  return (
    <VStack align="stretch" spacing={2}>
      {errorMessage ? (
        <Alert status="error" borderRadius="md" fontSize="sm">
          <AlertIcon />
          <AlertDescription>{errorMessage}</AlertDescription>
        </Alert>
      ) : null}
      {isDegraded ? (
        <Alert status="warning" borderRadius="md" fontSize="sm">
          <AlertIcon />
          <AlertDescription>{METERING.BANNERS.DEGRADED}</AlertDescription>
        </Alert>
      ) : null}
    </VStack>
  );
};

interface MeteringAsyncStateProps {
  isLoading?: boolean;
  isEmpty?: boolean;
  errorMessage?: string | null;
  emptyMessage?: string;
  height?: string | number;
  children: React.ReactNode;
}

/** Loading / error / empty wrapper for tab content. */
const MeteringAsyncState: React.FC<MeteringAsyncStateProps> = ({
  isLoading = false,
  isEmpty = false,
  errorMessage,
  emptyMessage = METERING.EMPTY.DEFAULT,
  height = METERING.DEFAULTS.ASYNC_STATE_HEIGHT,
  children,
}) => {
  if (isLoading) {
    return (
      <Center h={height}>
        <Spinner size="lg" color="orange.500" />
      </Center>
    );
  }

  if (errorMessage) {
    return (
      <Alert status="error" borderRadius="md" fontSize="sm">
        <AlertIcon />
        <AlertDescription>{errorMessage}</AlertDescription>
      </Alert>
    );
  }

  if (isEmpty) {
    return (
      <Center h={height}>
        <Text color="gray.500">{emptyMessage}</Text>
      </Center>
    );
  }

  return <>{children}</>;
};

export default MeteringAsyncState;
