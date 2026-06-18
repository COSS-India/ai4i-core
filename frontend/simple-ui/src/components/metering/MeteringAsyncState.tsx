import { Alert, AlertDescription, AlertIcon, Center, Spinner, Text } from "@chakra-ui/react";
import React from "react";

interface MeteringAsyncStateProps {
  isLoading?: boolean;
  isEmpty?: boolean;
  errorMessage?: string | null;
  emptyMessage?: string;
  height?: string | number;
  children: React.ReactNode;
}

const MeteringAsyncState: React.FC<MeteringAsyncStateProps> = ({
  isLoading = false,
  isEmpty = false,
  errorMessage,
  emptyMessage = "No data available.",
  height = "300px",
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
