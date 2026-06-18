import { Alert, AlertDescription, AlertIcon } from "@chakra-ui/react";
import React from "react";

interface MeteringStatusBannersProps {
  isMock?: boolean;
  isDegraded?: boolean;
  errorMessage?: string | null;
}

const MeteringStatusBanners: React.FC<MeteringStatusBannersProps> = ({
  isMock = false,
  isDegraded = false,
  errorMessage,
}) => (
  <>
    {errorMessage ? (
      <Alert status="error" borderRadius="md" fontSize="sm">
        <AlertIcon />
        <AlertDescription>{errorMessage}</AlertDescription>
      </Alert>
    ) : null}
    {isDegraded ? (
      <Alert status="warning" borderRadius="md" fontSize="sm">
        <AlertIcon />
        <AlertDescription>
          Some metrics could not be loaded completely. Showing partial data from the metering API.
        </AlertDescription>
      </Alert>
    ) : null}
    {isMock ? (
      <Alert status="info" borderRadius="md" fontSize="sm">
        <AlertIcon />
        <AlertDescription>
          Showing sample data — set{" "}
          <code>NEXT_PUBLIC_METERING_USE_MOCK=false</code> and connect to the metering API for live
          metrics.
        </AlertDescription>
      </Alert>
    ) : null}
  </>
);

export default MeteringStatusBanners;
