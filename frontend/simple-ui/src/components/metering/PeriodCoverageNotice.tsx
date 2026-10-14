import { Alert, AlertDescription, AlertIcon } from "@chakra-ui/react";
import React from "react";
import type { MeteringPeriodEcho } from "../../types/metering";
import { periodCoverageNotice } from "../../utils/meteringCoverage";

/**
 * A tab's note on how much of the period its figures cover: missing days at
 * its start, and estimated days (see periodCoverageNotice). Renders nothing
 * when the period is fully covered by recorded data.
 */
const PeriodCoverageNotice: React.FC<{ period?: MeteringPeriodEcho | null }> = ({ period }) => {
  const message = periodCoverageNotice(period);
  if (!message) return null;
  return (
    <Alert status="info" borderRadius="md" fontSize="sm">
      <AlertIcon />
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  );
};

export default PeriodCoverageNotice;
