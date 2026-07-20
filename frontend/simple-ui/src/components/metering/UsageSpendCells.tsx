import { Box, Center, Flex, HStack, Text } from "@chakra-ui/react";
import React from "react";
import { formatModelTaskTypeLabel } from "../../config/constants";
import {
  USAGE_SPEND_DANGER,
  USAGE_SPEND_WARNING,
  formatSpendMoney,
  formatSpendUnit,
  spendBarColor,
  tenantAvatarBg,
  tenantInitials,
} from "../../utils/usageSpendHelpers";

export function RatioBar({
  pct,
  main,
  of,
  caption,
  captionTone,
}: {
  pct: number;
  main: string;
  of: string;
  caption: string;
  captionTone?: "over" | "warn" | "muted";
}) {
  const fillPct = Math.min(Math.max(pct, 0), 100);
  // Keep a visible sliver for tiny-but-nonzero usage that would otherwise round to a 0px fill.
  const visualFillPct = fillPct > 0 && fillPct < 2 ? 2 : fillPct;
  const captionColor =
    captionTone === "over" ? USAGE_SPEND_DANGER : captionTone === "warn" ? USAGE_SPEND_WARNING : "gray.500";

  return (
    <Box minW="170px">
      <Flex justify="space-between" fontSize="12.5px" mb="6px">
        <Text fontWeight="semibold">{main}</Text>
        <Text color="gray.500" fontWeight="normal">
          {of}
        </Text>
      </Flex>
      <Box
        h="6px"
        borderRadius="3px"
        bg="gray.200"
        borderWidth="1px"
        borderColor="gray.300"
        overflow="hidden"
      >
        <Box h="100%" w={`${visualFillPct}%`} bg={spendBarColor(pct)} borderRadius="3px" />
      </Box>
      <Text
        fontSize="11.5px"
        mt="5px"
        color={captionColor}
        fontWeight={captionTone === "over" || captionTone === "warn" ? "semibold" : "normal"}
      >
        {caption}
      </Text>
    </Box>
  );
}

export function BudgetCell({
  limit,
  spent,
  remaining,
  percentageUsed,
  currency,
}: {
  limit: number;
  spent: number;
  remaining: number;
  percentageUsed: number;
  currency: string;
}) {
  const pct = percentageUsed || (limit > 0 ? (spent / limit) * 100 : 0);
  const over = spent - limit;
  let caption: string;
  let tone: "over" | "warn" | "muted" = "muted";
  if (over > 0) {
    caption = `${formatSpendMoney(over, currency)} over budget`;
    tone = "over";
  } else if (pct >= 90) {
    caption = `${formatSpendMoney(remaining, currency)} left · ${pct.toFixed(0)}% used`;
    tone = "warn";
  } else {
    caption = `${formatSpendMoney(remaining, currency)} left`;
  }

  return (
    <RatioBar
      pct={pct}
      main={`${pct.toFixed(0)}% used`}
      of={`of ${formatSpendMoney(limit, currency)}`}
      caption={caption}
      captionTone={tone}
    />
  );
}

export function UsageCell({
  consumed,
  quotaLimit,
  remaining,
  percentage,
  unit,
}: {
  consumed: number;
  quotaLimit: number;
  remaining: number;
  percentage: number;
  unit: string;
}) {
  const pct = percentage || (quotaLimit > 0 ? (consumed / quotaLimit) * 100 : 0);
  return (
    <RatioBar
      pct={pct}
      main={formatSpendUnit(consumed, unit)}
      of={`of ${formatSpendUnit(quotaLimit, unit)}`}
      caption={`${formatSpendUnit(Math.max(remaining, 0), unit)} left · ${pct.toFixed(0)}%`}
    />
  );
}

export function TierBadge({ label }: { label: string }) {
  return (
    <Text
      fontSize="10px"
      fontWeight="bold"
      letterSpacing="0.03em"
      bg="gray.50"
      borderWidth="1px"
      borderColor="gray.200"
      color="gray.600"
      px="9px"
      py="3px"
      borderRadius="5px"
      display="inline-block"
    >
      {label.toUpperCase()}
    </Text>
  );
}

export function TenantAvatar({
  name,
  size = "sm",
}: {
  name: string;
  size?: "sm" | "md";
}) {
  const dim = size === "md" ? "36px" : "26px";
  const fontSize = size === "md" ? "14px" : "11px";
  return (
    <Center
      w={dim}
      h={dim}
      borderRadius="full"
      bg={tenantAvatarBg(name)}
      color="white"
      fontSize={fontSize}
      fontWeight="bold"
      flexShrink={0}
    >
      {tenantInitials(name)}
    </Center>
  );
}

export function TaskTypeLabel({
  taskType,
  color,
  fontSize = "13px",
  fontWeight = "medium",
}: {
  taskType: string;
  color: string;
  fontSize?: string;
  fontWeight?: string;
}) {
  return (
    <HStack spacing={2} fontSize={fontSize} fontWeight={fontWeight}>
      <Box w="8px" h="8px" borderRadius="full" bg={color} flexShrink={0} />
      <Text>{formatModelTaskTypeLabel(taskType)}</Text>
    </HStack>
  );
}
