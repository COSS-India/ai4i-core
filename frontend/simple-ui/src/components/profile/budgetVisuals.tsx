import { Box, Flex, HStack, Text } from "@chakra-ui/react";
import React from "react";
import { FiCheckCircle, FiCreditCard, FiPieChart } from "react-icons/fi";
import { formatSpendMoney } from "../../utils/usageSpendHelpers";
import { BUDGET_COPY } from "../../config/budgetMessages";

/** Reference budget dialogs use two-decimal percentages. */
export function formatBudgetPct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${(Math.round(value * 100) / 100).toFixed(2)}%`;
}

export function formatBudgetMoney(
  amount: number | null | undefined,
  currency = "INR",
): string {
  if (amount == null || !Number.isFinite(amount)) return "—";
  return formatSpendMoney(amount, currency);
}

const TONE = {
  allocated: {
    bg: "blue.50",
    border: "blue.100",
    label: "blue.700",
    sub: "blue.600",
    iconBg: "blue.100",
    icon: "blue.600",
  },
  consumed: {
    bg: "orange.50",
    border: "orange.100",
    label: "orange.700",
    sub: "orange.600",
    iconBg: "orange.100",
    icon: "orange.600",
  },
  remaining: {
    bg: "green.50",
    border: "green.100",
    label: "green.700",
    sub: "green.600",
    iconBg: "green.100",
    icon: "green.700",
  },
} as const;

function StatIcon({ tone }: { tone: keyof typeof TONE }) {
  const color = TONE[tone].icon;
  const icon =
    tone === "allocated" ? (
      <FiCreditCard size={14} />
    ) : tone === "consumed" ? (
      <FiPieChart size={14} />
    ) : (
      <FiCheckCircle size={14} />
    );
  return (
    <Flex
      w="26px"
      h="26px"
      borderRadius="8px"
      bg={TONE[tone].iconBg}
      color={color}
      align="center"
      justify="center"
      mb="8px"
      flexShrink={0}
    >
      {icon}
    </Flex>
  );
}

export type BudgetStat = {
  tone: keyof typeof TONE;
  label: string;
  value: string;
  sub?: string;
  /** Share of the parent budget, 0–100. Drawn only when set. */
  progress?: number | null;
  progressOver?: boolean;
  flex?: number;
};

/** Tinted Allocated / Consumed / Remaining strip used by every budget dialog. */
export function BudgetContextStrip({ stats }: { stats: BudgetStat[] }) {
  return (
    <Flex gap="10px" align="stretch" wrap="wrap">
      {stats.map((stat) => {
        const tone = TONE[stat.tone];
        const progress =
          stat.progress == null || !Number.isFinite(stat.progress)
            ? null
            : Math.max(0, Math.min(stat.progress, 100));
        return (
          <Box
            key={stat.label}
            flex={stat.flex ?? 1}
            minW={{ base: "100%", md: "0" }}
            bg={tone.bg}
            borderWidth="1px"
            borderColor={tone.border}
            borderRadius="12px"
            px="12px"
            py="13px"
            textAlign="left"
          >
            <StatIcon tone={stat.tone} />
            <Text
              fontSize="10px"
              fontWeight="700"
              letterSpacing="0.3px"
              textTransform="uppercase"
              color={tone.label}
              mb="3px"
              lineHeight="1.2"
            >
              {stat.label}
            </Text>
            <Text fontSize="17px" fontWeight="800" color="ink.800" lineHeight="1.2" noOfLines={2}>
              {stat.value}
            </Text>
            {stat.sub ? (
              <Text fontSize="11px" fontWeight="600" color={tone.sub} mt="2px" lineHeight="1.3">
                {stat.sub}
              </Text>
            ) : null}
            {progress != null ? (
              <Box mt="8px" h="5px" bg="ink.200" borderRadius="full" overflow="hidden">
                <Box
                  h="100%"
                  bg={stat.progressOver ? "red.500" : "blue.500"}
                  w={`${progress}%`}
                />
              </Box>
            ) : null}
          </Box>
        );
      })}
    </Flex>
  );
}

export function BudgetRangeBox({ value }: { value: string }) {
  return (
    <Flex
      align="center"
      justify="space-between"
      gap={3}
      bg="ink.50"
      borderWidth="1px"
      borderColor="ink.200"
      borderRadius="10px"
      px="14px"
      py="11px"
    >
      <Text
        fontSize="11px"
        fontWeight="700"
        color="ink.400"
        textTransform="uppercase"
        letterSpacing="0.3px"
        flexShrink={0}
      >
        Allowed range
      </Text>
      <Text fontSize="14px" fontWeight="800" color="ink.800" textAlign="right">
        {value}
      </Text>
    </Flex>
  );
}

/** Saved percent with rupees underneath, matching the reference table cells. */
export function BudgetAmountCell({
  primary,
  secondary,
  valueColor = "ink.800",
}: {
  primary: string;
  secondary?: string;
  valueColor?: string;
}) {
  return (
    <Box minW={0}>
      <Text fontSize="13px" fontWeight="700" color={valueColor} lineHeight="1.3">
        {primary}
      </Text>
      {secondary ? (
        <Text fontSize="11px" fontWeight="600" color="ink.500" mt="1px">
          {secondary}
        </Text>
      ) : null}
    </Box>
  );
}

export function RevokeBudgetBreakdown({
  status,
  allocated,
  consumed,
  unused,
  applicationName,
}: {
  status: "loading" | "ready" | "error";
  allocated?: number;
  consumed?: number;
  unused?: number;
  applicationName?: string;
}) {
  if (status === "error") {
    return (
      <Text fontSize="13px" color="ink.600" lineHeight="1.5">
        Budget usage could not be loaded. Allocated, consumed, and unused amounts are
        unavailable.
      </Text>
    );
  }

  const value = (amount: number | undefined) =>
    status === "loading" ? BUDGET_COPY.loading : formatBudgetMoney(amount);

  const rows: {
    label: string;
    hint?: string;
    value: string;
    tone: "total" | "plain" | "return";
  }[] = [
    { label: "Total Allocated", value: value(allocated), tone: "total" },
    { label: "Already Consumed", value: value(consumed), tone: "plain" },
    {
      label: "Unused",
      hint:
        status === "ready" && applicationName
          ? `Returns to ${applicationName}`
          : undefined,
      value: value(unused),
      tone: "return",
    },
  ];

  return (
    <Box borderWidth="1px" borderColor="ink.200" borderRadius="12px" overflow="hidden">
      {rows.map((row, index) => (
        <HStack
          key={row.label}
          justify="space-between"
          align="center"
          spacing={4}
          px="16px"
          py="12px"
          bg={row.tone === "total" ? "blue.50" : row.tone === "return" ? "green.50" : "white"}
          borderBottomWidth={index < rows.length - 1 ? "1px" : 0}
          borderColor="ink.200"
        >
          <Box minW={0}>
            <Text
              fontSize="12.5px"
              fontWeight={row.tone === "total" ? "700" : "600"}
              color={row.tone === "return" ? "green.700" : row.tone === "total" ? "ink.800" : "ink.600"}
            >
              {row.label}
            </Text>
            {row.hint ? (
              <Text fontSize="10.5px" fontWeight="600" color="green.600" mt="1px">
                {row.hint}
              </Text>
            ) : null}
          </Box>
          <Text
            fontSize="14.5px"
            fontWeight="800"
            color={row.tone === "return" ? "green.700" : "ink.800"}
            flexShrink={0}
          >
            {row.value}
          </Text>
        </HStack>
      ))}
    </Box>
  );
}
