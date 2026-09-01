import { Box, HStack, SimpleGrid, Text } from "@chakra-ui/react";
import React from "react";
import { METERING } from "../../config/meteringConstants";
import type { ApplicationUsageSummary } from "../../types/applicationUsage";
import {
  formatSpendMoney,
  USAGE_SPEND_ACCENT,
} from "../../utils/usageSpendHelpers";
import InfoTip from "../common/InfoTip";
import MeteringAsyncState from "./MeteringAsyncState";
import { formatApplicationPct, SummaryPctPill } from "./ApplicationUsageCells";

const CARD_BG = "#eef3fb";

function SummaryCard({
  label,
  tooltip,
  primary,
  scope,
  pctLabel,
}: {
  label: string;
  tooltip: string;
  primary: string;
  scope?: string;
  pctLabel?: string;
}) {
  return (
    <Box
      bg={CARD_BG}
      borderRadius="14px"
      borderWidth="1px"
      borderColor="gray.200"
      p="20px 22px"
      minW={0}
      minH="110px"
      display="flex"
      flexDirection="column"
    >
      <HStack spacing={1.5} mb={3} align="center">
        <Text
          fontSize="12.5px"
          fontWeight="bold"
          letterSpacing="0.05em"
          color={USAGE_SPEND_ACCENT}
        >
          {label}
        </Text>
        <InfoTip message={tooltip} />
      </HStack>
      <Text fontSize="24px" fontWeight="extrabold" lineHeight="1.1" color="gray.800" noOfLines={1}>
        {primary}
      </Text>
      {scope ? (
        <Text fontSize="12px" color="gray.500" mt={2}>
          {scope}
        </Text>
      ) : null}
      {pctLabel ? <SummaryPctPill label={pctLabel} /> : null}
    </Box>
  );
}

interface ApplicationUsageSummaryPanelProps {
  summary?: ApplicationUsageSummary;
  isLoading: boolean;
  error: string | null;
  currency?: string;
}

const ApplicationUsageSummaryPanel: React.FC<ApplicationUsageSummaryPanelProps> = ({
  summary,
  isLoading,
  error,
  currency = "INR",
}) => {
  const copy = METERING.APPLICATION_USAGE;
  const pctSuffix = copy.SUMMARY.PCT_OF_INSTITUTION;

  return (
    <MeteringAsyncState
      isLoading={isLoading}
      isEmpty={!isLoading && !summary}
      errorMessage={error}
      emptyMessage={copy.EMPTY}
    >
      {summary ? (
        <SimpleGrid columns={{ base: 1, sm: 2, lg: 4 }} spacing={5}>
          <SummaryCard
            label={copy.SUMMARY.TOTAL_APPLICATIONS}
            tooltip={copy.TOOLTIPS.TOTAL_APPLICATIONS}
            primary={String(summary.totalApplications)}
            scope={copy.SUMMARY.SCOPE_ONBOARDED}
          />
          <SummaryCard
            label={copy.SUMMARY.ALLOCATED}
            tooltip={copy.TOOLTIPS.ALLOCATED}
            primary={formatSpendMoney(summary.allocatedBudget.amount, currency)}
            scope={copy.SUMMARY.SCOPE_ACROSS_APPS}
            pctLabel={`${formatApplicationPct(summary.allocatedBudget.percentage)} ${pctSuffix}`}
          />
          <SummaryCard
            label={copy.SUMMARY.SPENT}
            tooltip={copy.TOOLTIPS.SPENT}
            primary={formatSpendMoney(summary.spendBudget.amount, currency)}
            scope={copy.SUMMARY.SCOPE_ACROSS_APPS}
            pctLabel={`${formatApplicationPct(summary.spendBudget.percentage)} ${pctSuffix}`}
          />
          <SummaryCard
            label={copy.SUMMARY.REMAINING}
            tooltip={copy.TOOLTIPS.REMAINING}
            primary={formatSpendMoney(summary.remainingBudget.amount, currency)}
            scope={copy.SUMMARY.SCOPE_ACROSS_APPS}
            pctLabel={`${formatApplicationPct(summary.remainingBudget.percentage)} ${pctSuffix}`}
          />
        </SimpleGrid>
      ) : null}
    </MeteringAsyncState>
  );
};

export default ApplicationUsageSummaryPanel;
