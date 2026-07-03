import { Alert, AlertDescription, AlertIcon, Center, Spinner, Text, VStack } from "@chakra-ui/react";
import React from "react";
import { METERING } from "../../config/meteringConstants";

interface MeteringAlertsProps {
  errorMessage?: string | null;
  dataStateBanner?: { status: "error" | "info"; message: string } | null;
}

/** Dashboard-level HTTP errors and API `data_state` banners. */
export const MeteringAlerts: React.FC<MeteringAlertsProps> = ({
  errorMessage,
  dataStateBanner,
}) => {
  if (!errorMessage && !dataStateBanner) return null;

  return (
    <VStack align="stretch" spacing={2}>
      {errorMessage ? (
        <Alert status="error" borderRadius="md" fontSize="sm">
          <AlertIcon />
          <AlertDescription>{errorMessage}</AlertDescription>
        </Alert>
      ) : null}
      {dataStateBanner ? (
        <Alert status={dataStateBanner.status} borderRadius="md" fontSize="sm">
          <AlertIcon />
          <AlertDescription>{dataStateBanner.message}</AlertDescription>
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
