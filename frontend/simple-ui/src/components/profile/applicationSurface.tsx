import {
  Box,
  Button,
  Flex,
  HStack,
  SimpleGrid,
  Skeleton,
  Text,
  VStack,
} from "@chakra-ui/react";
import React from "react";
import CreateButton from "../common/CreateButton";
import { BUDGET_COPY } from "../../config/budgetMessages";
import { formatBudgetMoney, formatBudgetPct } from "./budgetVisuals";

function money(amount: number | null | undefined, currency: string): string {
  return formatBudgetMoney(amount, currency);
}

const STATUS_DOT = {
  success: { dot: "green.500", text: "ink.800" },
  warning: { dot: "orange.400", text: "ink.800" },
  danger: { dot: "red.500", text: "ink.700" },
  neutral: { dot: "ink.300", text: "ink.500" },
} as const;

export function StatusDot({
  label,
  tone,
}: {
  label: string;
  tone: keyof typeof STATUS_DOT;
}) {
  const colors = STATUS_DOT[tone];
  return (
    <HStack spacing={2} align="center">
      <Box w="6px" h="6px" borderRadius="full" bg={colors.dot} flexShrink={0} aria-hidden />
      <Text fontSize="sm" fontWeight="500" color={colors.text}>
        {label}
      </Text>
    </HStack>
  );
}

export function ApplicationStatusText({ status }: { status: string }) {
  const active = status === "ACTIVE";
  return <StatusDot label={active ? "Active" : "Inactive"} tone={active ? "success" : "neutral"} />;
}

export function applicationInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return name.slice(0, 2).toUpperCase() || "AP";
}

export function EntityIdentity({
  name,
  detail,
  meta,
}: {
  name: string;
  detail?: string | null;
  meta?: string | null;
}) {
  const detailText = detail?.trim() || "";
  const metaText = meta?.trim() || "";
  return (
    <HStack spacing={3} align="center" minW={0}>
      <Flex
        w="32px"
        h="32px"
        borderRadius="md"
        bg="ink.100"
        color="ink.700"
        fontSize="11px"
        fontWeight="700"
        align="center"
        justify="center"
        flexShrink={0}
        aria-hidden
      >
        {applicationInitials(name)}
      </Flex>
      <Box minW={0}>
        <Text fontSize="sm" fontWeight="700" color="ink.800" noOfLines={1} title={name}>
          {name}
        </Text>
        {detailText ? (
          <Text fontSize="xs" color="ink.500" noOfLines={1} title={detailText}>
            {detailText}
          </Text>
        ) : null}
        {metaText ? (
          <Text fontSize="xs" color="ink.400" noOfLines={1} title={metaText}>
            {metaText}
          </Text>
        ) : null}
      </Box>
    </HStack>
  );
}

export function ApplicationIdentity({
  name,
  description,
  domain,
}: {
  name: string;
  description?: string | null;
  domain?: string | null;
}) {
  return <EntityIdentity name={name} detail={description} meta={domain} />;
}

function Metric({
  label,
  value,
  sub,
  valueColor = "ink.800",
  subColor = "ink.500",
  subFontWeight,
}: {
  label: string;
  value: string;
  sub?: string;
  valueColor?: string;
  subColor?: string;
  subFontWeight?: string;
}) {
  return (
    <Box minW={0}>
      <Text
        fontSize="11px"
        fontWeight="600"
        letterSpacing="0.04em"
        textTransform="uppercase"
        color="ink.500"
        mb={1}
      >
        {label}
      </Text>
      <Text fontSize="26px" fontWeight="700" letterSpacing="-0.03em" color={valueColor} lineHeight="1.1">
        {value}
      </Text>
      {sub ? (
        <Text fontSize="xs" fontWeight={subFontWeight} color={subColor} mt={1} noOfLines={2}>
          {sub}
        </Text>
      ) : null}
    </Box>
  );
}

function AllocationBar({
  allocatedPct,
  availablePct,
  overAllocated,
  label,
}: {
  allocatedPct: number;
  availablePct: number;
  overAllocated: boolean;
  label: string;
}) {
  const allocated = Math.max(0, Math.min(allocatedPct, 100));
  const available = overAllocated ? 0 : Math.max(0, Math.min(availablePct, 100 - allocated));
  return (
    <Flex
      h="8px"
      bg="ink.100"
      borderRadius="full"
      overflow="hidden"
      role="img"
      aria-label={label}
    >
      <Box h="100%" w={`${allocated}%`} bg={overAllocated ? "red.500" : "blue.500"} />
      {available > 0 ? <Box h="100%" w={`${available}%`} bg="green.400" /> : null}
    </Flex>
  );
}

/** Institution allocation as one panel: counts, committed share, remaining capacity, and a single bar. */
export function InstitutionAllocationPanel({
  applicationCount,
  countLabel = "Applications",
  countSub = "Under this institution",
  allocatedCaption = "committed",
  availableCaption = "still unassigned",
  allocatedPct = 0,
  availablePct = 0,
  institutionBudget,
  currency,
  overAllocated = false,
  figures = "percent",
  allocatedAmount: allocatedAmountProp,
  showAvailable = true,
  showBar = true,
  overMessage = "Allocation exceeds the institution budget.",
  context,
}: {
  applicationCount?: number;
  countLabel?: string;
  countSub?: string;
  allocatedCaption?: string;
  availableCaption?: string;
  allocatedPct?: number;
  availablePct?: number;
  institutionBudget: number;
  currency: string;
  overAllocated?: boolean;
  figures?: "percent" | "amount";
  allocatedAmount?: number | null;
  showAvailable?: boolean;
  showBar?: boolean;
  overMessage?: string;
  context?: { label: string; value: string; sub?: string };
}) {
  const allocatedAmount =
    allocatedAmountProp !== undefined
      ? allocatedAmountProp
      : institutionBudget > 0
        ? (allocatedPct / 100) * institutionBudget
        : null;
  const availableAmount =
    institutionBudget > 0 ? (availablePct / 100) * institutionBudget : null;
  const fill = Math.max(0, Math.min(allocatedPct, 100));
  const allocatedValue =
    figures === "amount" ? money(allocatedAmount, currency) : formatBudgetPct(allocatedPct);
  const availableValue =
    figures === "amount" ? money(availableAmount, currency) : formatBudgetPct(availablePct);
  const allocatedSub =
    figures === "amount" ? allocatedCaption : `${money(allocatedAmount, currency)} ${allocatedCaption}`;
  const availableSub =
    figures === "amount" ? availableCaption : `${money(availableAmount, currency)} ${availableCaption}`;

  const barLabel = overAllocated
    ? `Allocated ${formatBudgetPct(allocatedPct)}. ${overMessage} Available ${formatBudgetPct(availablePct)}.`
    : `Allocated ${formatBudgetPct(allocatedPct)}, available ${formatBudgetPct(availablePct)}.`;
  const columns =
    (context ? 1 : 0) + (applicationCount == null ? 0 : 1) + 1 + (showAvailable ? 1 : 0);

  return (
    <Box borderWidth="1px" borderColor="ink.200" borderRadius="lg" bg="ink.50" px={{ base: 4, md: 5 }} py={4}>
      <SimpleGrid columns={{ base: 1, md: columns }} spacing={{ base: 4, md: 6 }}>
        {context ? (
          <Metric label={context.label} value={context.value} sub={context.sub} />
        ) : null}
        {applicationCount == null ? null : (
          <Metric label={countLabel} value={String(applicationCount)} sub={countSub} />
        )}
        <Metric
          label="Allocated"
          value={allocatedValue}
          sub={allocatedSub}
          valueColor={overAllocated ? "red.600" : "blue.700"}
        />
        {showAvailable ? (
          <Metric
            label="Available"
            value={availableValue}
            sub={availableSub}
            valueColor="green.700"
          />
        ) : null}
      </SimpleGrid>
      {showBar ? (
        <Box mt={4}>
          <AllocationBar
            allocatedPct={fill}
            availablePct={availablePct}
            overAllocated={overAllocated}
            label={barLabel}
          />
          {overAllocated ? (
            <Text mt={2} fontSize="xs" fontWeight="600" color="red.600">
              {overMessage}
            </Text>
          ) : null}
        </Box>
      ) : null}
    </Box>
  );
}

/** One application's saved allocation, what it has spent, and what it still has left. */
export function ApplicationBudgetFacts({
  allocatedPct,
  allocatedAmount,
  allocatedLabel,
  consumedLabel,
  consumedSub,
  remainingLabel = BUDGET_COPY.remaining,
  remainingValue,
  remainingSub,
  remainingColor = "ink.800",
  remainingSubColor,
  remainingNegative = false,
  rangeLabel,
  currency,
}: {
  allocatedPct: number | null | undefined;
  allocatedAmount: number | null | undefined;
  /** Replaces the formatted percentage while usage is still loading. */
  allocatedLabel?: string;
  consumedLabel: string;
  consumedSub?: string;
  /** Headline for the third metric. */
  remainingLabel?: string;
  remainingValue: string;
  remainingSub?: string;
  remainingColor?: string;
  /** Keeps a negative rupee remainder in the same error color as the percentage. */
  remainingSubColor?: string;
  /** Tints the remaining column when this application is already over-consumed. */
  remainingNegative?: boolean;
  rangeLabel: string;
  currency: string;
}) {
  const factPad = { px: { base: 4, md: 5 }, py: 4 };
  return (
    <Box borderWidth="1px" borderColor="ink.200" borderRadius="lg" bg="ink.50" overflow="hidden">
      <SimpleGrid columns={{ base: 1, sm: 3 }} spacing={0}>
        <Box
          {...factPad}
          borderColor="ink.200"
          borderBottomWidth={{ base: "1px", sm: 0 }}
          borderRightWidth={{ sm: "1px" }}
        >
          <Metric
            label="Allocated"
            value={allocatedLabel ?? formatBudgetPct(allocatedPct)}
            sub={
              allocatedLabel && allocatedAmount == null
                ? undefined
                : money(allocatedAmount, currency)
            }
            valueColor="blue.700"
            subFontWeight="600"
          />
        </Box>
        <Box
          {...factPad}
          borderColor="ink.200"
          borderBottomWidth={{ base: "1px", sm: 0 }}
          borderRightWidth={{ sm: "1px" }}
        >
          <Metric label="Consumed" value={consumedLabel} sub={consumedSub} subFontWeight="600" />
        </Box>
        <Box {...factPad} bg={remainingNegative ? "red.50" : undefined}>
          <Metric
            label={remainingLabel}
            value={remainingValue}
            sub={remainingSub}
            valueColor={remainingColor}
            subColor={remainingSubColor}
            subFontWeight="600"
          />
        </Box>
      </SimpleGrid>
      <Flex
        px={{ base: 4, md: 5 }}
        py={2.5}
        bg="white"
        borderTopWidth="1px"
        borderColor="ink.200"
        justify="space-between"
        align="center"
        gap={3}
      >
        <Text fontSize="11px" fontWeight="600" letterSpacing="0.04em" textTransform="uppercase" color="ink.500">
          Allowed range
        </Text>
        <Text fontSize="xs" fontWeight="600" color="ink.600" textAlign="right">
          {rangeLabel}
        </Text>
      </Flex>
    </Box>
  );
}

export function InstitutionAllocationSkeleton() {
  return (
    <Box borderWidth="1px" borderColor="ink.200" borderRadius="lg" bg="ink.50" overflow="hidden" aria-busy="true" aria-label="Loading applications">
      <SimpleGrid columns={{ base: 1, md: 3 }}>
        {[0, 1, 2].map((key) => (
          <Box key={key} px={5} py={4} borderColor="ink.100" borderRightWidth={{ md: key < 2 ? "1px" : 0 }}>
            <Skeleton h="10px" w="72px" mb={3} />
            <Skeleton h="22px" w="88px" mb={2} />
            <Skeleton h="10px" w="120px" />
          </Box>
        ))}
      </SimpleGrid>
      <Box px={5} py={3} borderTopWidth="1px" borderColor="ink.100">
        <Skeleton h="6px" borderRadius="full" />
      </Box>
    </Box>
  );
}

export function ApplicationEmptyState({
  onCreate,
  title = "No applications yet",
  body = "Create your first application to allocate institution budget.",
  actionLabel = "Create Application",
}: {
  onCreate: () => void;
  title?: string;
  body?: string;
  actionLabel?: string;
}) {
  return (
    <VStack
      spacing={3}
      py={10}
      px={6}
      textAlign="center"
    >
      <Text fontSize="md" fontWeight="600" color="ink.800">
        {title}
      </Text>
      <Text fontSize="sm" color="ink.500" maxW="360px">
        {body}
      </Text>
      <CreateButton mt={1} onClick={onCreate}>
        {actionLabel}
      </CreateButton>
    </VStack>
  );
}

export function ApplicationNoResults({
  onClear,
  title = "No matching applications",
  body = "Try another name or domain.",
  actionLabel = "Clear search",
}: {
  onClear: () => void;
  title?: string;
  body?: string;
  actionLabel?: string;
}) {
  return (
    <VStack
      spacing={2}
      py={8}
      px={6}
      textAlign="center"
    >
      <Text fontSize="sm" fontWeight="600" color="ink.800">
        {title}
      </Text>
      <Text fontSize="sm" color="ink.500">
        {body}
      </Text>
      <Button size="sm" variant="outline" onClick={onClear}>
        {actionLabel}
      </Button>
    </VStack>
  );
}

export function ApplicationLoadError({ onRetry }: { onRetry: () => void }) {
  return (
    <VStack
      spacing={2}
      align="flex-start"
      py={5}
      px={5}
      borderWidth="1px"
      borderColor="red.100"
      borderRadius="lg"
      bg="red.50"
    >
      <Text fontSize="sm" fontWeight="600" color="red.800">
        Unable to load applications
      </Text>
      <Text fontSize="sm" color="red.700">
        Please try again.
      </Text>
      <Button size="sm" variant="outline" colorScheme="red" onClick={onRetry}>
        Retry
      </Button>
    </VStack>
  );
}
