import { Box, Center, Flex, HStack, Text, Tooltip } from "@chakra-ui/react";
import React from "react";
import { formatModelTaskTypeLabel } from "../../config/constants";
import {
  USAGE_SPEND_DANGER,
  USAGE_SPEND_WARNING,
  formatSpendMoney,
  formatSpendUnit,
  formatSpendUnitCompact,
  formatSpendUnitExact,
  spendBarColor,
  tenantAvatarBg,
  tenantInitials,
} from "../../utils/usageSpendHelpers";

export type RatioBarCaptionTone = "over" | "warn" | "muted";
/** "topRight": used amount top-right, available amount bottom-left, with a hover tooltip. */
export type RatioBarLayout = "standard" | "topRight";

export function RatioBar({
  pct,
  main,
  of,
  caption,
  captionTone,
  layout = "standard",
  tooltip,
}: {
  pct: number;
  main: string;
  of?: string;
  caption: string;
  captionTone?: RatioBarCaptionTone;
  layout?: RatioBarLayout;
  /** Hover tooltip over the bar itself, e.g. "72% used · 28% remaining". */
  tooltip?: string;
}) {
  const fillPct = Math.min(Math.max(pct, 0), 100);
  // Keep a visible sliver for tiny-but-nonzero usage that would otherwise round to a 0px fill.
  const visualFillPct = fillPct > 0 && fillPct < 2 ? 2 : fillPct;
  const captionColor =
    captionTone === "over" ? USAGE_SPEND_DANGER : captionTone === "warn" ? USAGE_SPEND_WARNING : "gray.500";
  const captionWeight = captionTone === "over" || captionTone === "warn" ? "semibold" : "normal";

  const bar = (
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
  );
  const wrappedBar = tooltip ? (
    <Tooltip label={tooltip} hasArrow placement="top" openDelay={200}>
      <Box>{bar}</Box>
    </Tooltip>
  ) : (
    bar
  );

  if (layout === "topRight") {
    return (
      <Box minW="170px">
        <Flex justify="flex-end" fontSize="12.5px" mb="6px" whiteSpace="nowrap">
          <Text fontWeight="semibold">{main}</Text>
        </Flex>
        {wrappedBar}
        <Text
          fontSize="11.5px"
          mt="5px"
          color={captionColor}
          fontWeight={captionWeight}
          textAlign="left"
          whiteSpace="nowrap"
          overflow="hidden"
          textOverflow="ellipsis"
        >
          {caption}
        </Text>
      </Box>
    );
  }

  return (
    <Box minW="170px">
      <Flex align="baseline" gap="10px" fontSize="12.5px" mb="6px" whiteSpace="nowrap">
        <Text fontWeight="semibold">{main}</Text>
        <Text color="gray.500" fontWeight="normal" ml="auto">
          {of}
        </Text>
      </Flex>
      {wrappedBar}
      <Text
        fontSize="11.5px"
        mt="5px"
        color={captionColor}
        fontWeight={captionWeight}
        whiteSpace="nowrap"
        overflow="hidden"
        textOverflow="ellipsis"
      >
        {caption}
      </Text>
    </Box>
  );
}

export function ratioTooltip(pct: number): string {
  // Budget/quota tracking is post-hoc (see AI4IDS-2786) — real spend/consumption
  // can genuinely exceed the limit before enforcement catches up, so pct here
  // can arrive >100. Never show that as "used" text; 100/0 are the true bounds.
  const used = Math.min(100, Math.max(0, Math.round(pct)));
  const remaining = Math.max(0, Math.round(100 - pct));
  return `${used}% used · ${remaining}% remaining`;
}

export function BudgetCell({
  limit,
  spent,
  remaining,
  percentageUsed,
  deficit = 0,
  currency,
  layout = "standard",
}: {
  limit: number;
  spent: number;
  /** Already floored at 0 by the backend — never negative. */
  remaining: number;
  percentageUsed: number;
  /** Prior-period wallet deficit still owed, as a positive magnitude (0 if none). */
  deficit?: number;
  currency: string;
  layout?: RatioBarLayout;
}) {
  // ?? not ||: a legitimately clamped 0 must not fall through to the raw recompute.
  const pct = percentageUsed ?? (limit > 0 ? (spent / limit) * 100 : 0);
  // Budget enforcement is post-hoc (AI4IDS-2786) — pct can arrive >100 (spend
  // genuinely exceeded the limit before enforcement caught up). The bar width
  // (via RatioBar's own fillPct) is already capped; displayPct caps the
  // percentage TEXT the same way so it never reads above 100/below 0 either.
  const displayPct = Math.min(100, Math.max(0, pct));
  const over = spent - limit;
  // spent <= limit this period, but the wallet still owes from a PRIOR period
  // (remaining is floored, so it can't signal this itself — that's what
  // deficit is for). Distinct from `over`, which is this period's own
  // overshoot; a tenant can be fine this period and still carry a deficit.
  const hasDeficit = deficit > 0;

  if (layout === "topRight") {
    let caption: string;
    let tone: RatioBarCaptionTone = "muted";
    if (over > 0) {
      caption = `${formatSpendMoney(over, currency)} over budget`;
      tone = "over";
    } else if (hasDeficit) {
      caption = `${formatSpendMoney(deficit, currency)} owed from last period`;
      tone = "over";
    } else {
      caption = `${formatSpendMoney(remaining, currency)} available`;
      if (pct >= 90) tone = "warn";
    }
    return (
      <RatioBar
        pct={pct}
        main={formatSpendMoney(spent, currency)}
        caption={caption}
        captionTone={tone}
        layout="topRight"
        tooltip={ratioTooltip(pct)}
      />
    );
  }

  let caption: string;
  let tone: RatioBarCaptionTone = "muted";
  if (over > 0) {
    caption = `${formatSpendMoney(over, currency)} over budget`;
    tone = "over";
  } else if (hasDeficit) {
    caption = `${formatSpendMoney(deficit, currency)} owed from last period`;
    tone = "over";
  } else if (pct >= 90) {
    caption = `${formatSpendMoney(remaining, currency)} left · ${displayPct.toFixed(0)}% used`;
    tone = "warn";
  } else {
    caption = `${formatSpendMoney(remaining, currency)} left`;
  }

  return (
    <RatioBar
      pct={pct}
      main={`${displayPct.toFixed(0)}% used`}
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
  layout = "standard",
  compact = false,
}: Readonly<{
  consumed: number;
  quotaLimit?: number | null;
  remaining?: number | null;
  percentage?: number | null;
  unit: string;
  layout?: RatioBarLayout;
  compact?: boolean;
}>) {
  const limit = quotaLimit ?? 0;
  const used = consumed ?? 0;
  const left = remaining ?? Math.max(0, limit - used);
  const pct = percentage ?? (limit > 0 ? (used / limit) * 100 : 0);
  // Quota tracking is post-hoc (AI4IDS-2786) — pct can arrive >100. Cap the
  // displayed percentage text the same way the bar width is already capped.
  const displayPct = Math.min(100, Math.max(0, pct));
  const fmt = compact ? formatSpendUnitCompact : formatSpendUnit;
  const exactTooltip = `${formatSpendUnitExact(used, unit)} of ${formatSpendUnitExact(limit, unit)} · ${ratioTooltip(pct)}`;

  if (layout === "topRight") {
    return (
      <RatioBar
        pct={pct}
        main={fmt(used, unit)}
        caption={`${fmt(Math.max(left, 0), unit)} available`}
        captionTone={pct >= 90 ? "warn" : "muted"}
        layout="topRight"
        tooltip={compact ? exactTooltip : ratioTooltip(pct)}
      />
    );
  }

  return (
    <RatioBar
      pct={pct}
      main={fmt(used, unit)}
      of={`of ${fmt(limit, unit)}`}
      caption={`${fmt(Math.max(left, 0), unit)} left · ${displayPct.toFixed(0)}%`}
      tooltip={compact ? exactTooltip : undefined}
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
  const label = formatModelTaskTypeLabel(taskType);
  return (
    <HStack spacing={2} fontSize={fontSize} fontWeight={fontWeight} minW={0}>
      <Box w="8px" h="8px" borderRadius="full" bg={color} flexShrink={0} />
      <Tooltip label={label} hasArrow placement="top" openDelay={400}>
        <Text noOfLines={1}>{label}</Text>
      </Tooltip>
    </HStack>
  );
}
