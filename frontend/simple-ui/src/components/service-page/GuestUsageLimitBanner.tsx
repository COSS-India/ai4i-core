// Informational banner for guest users describing per-service hourly request limits

import { Alert, AlertDescription, AlertIcon, AlertTitle, Box } from "@chakra-ui/react";
import React from "react";
import { GUEST_REQUESTS_PER_HOUR_PER_SERVICE } from '../../constants';
import { useAuth } from "../../hooks/useAuth";
import { useGuestServices } from "../../hooks/useGuestServices";

const GuestUsageLimitBanner: React.FC = () => {
  const { isLoading: authLoading } = useAuth();
  const { isGuest } = useGuestServices();

  if (authLoading || !isGuest) {
    return null;
  }

  return (
    <Alert
      status="info"
      variant="left-accent"
      borderRadius="md"
      w="full"
      maxW="1200px"
      mx="auto"
    >
      <AlertIcon />
      <Box flex="1">
        <AlertTitle fontSize="md">Guest Usage Limit</AlertTitle>
        <AlertDescription fontSize="sm">
          You can make up to{" "}
          <strong>
            {GUEST_REQUESTS_PER_HOUR_PER_SERVICE} requests per service per hour
          </strong>.
        </AlertDescription>
      </Box>
    </Alert>
  );
};

export default GuestUsageLimitBanner;
