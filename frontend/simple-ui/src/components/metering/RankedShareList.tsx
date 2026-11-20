import { Box, Grid, HStack, Progress, Text, VStack } from "@chakra-ui/react";
import React from "react";
import { METERING } from "../../config/meteringConstants";
import { meteringColorAt } from "../../utils/meteringColors";
import { formatPercent } from "../../utils/meteringFormatters";
import { replaceTenantCopy } from "../../utils/replaceTenantCopy";
import InfoTip from "../common/InfoTip";
import MeteringTableText from "./MeteringTableText";
import { TaskTypeLabel } from "./UsageSpendCells";

export interface RankedShareRow {
  rank: number;
  label: string;
  /** Task type shown as its own column (Model consumption list). */
  subtitle?: string;
  /** Raw task type id — renders with TaskTypeLabel when set. */
  taskType?: string;
  formattedValue: string;
  percentage: number;
  color?: string;
}

interface RankedShareListProps {
  rows: RankedShareRow[];
  headerLeft?: string;
  headerTaskType?: string;
  headerTotal?: string;
  headerRight?: string;
  tipTotal?: string;
  tipTaskType?: string;
  tipRight?: string;
  /** Donut list: Model Name, Task Type, Total requests, % of total. */
  variant?: "default" | "modelWithTaskType";
  /**
   * Rounded decimals for the % column, shown with a "%" sign (Model tab: 1).
   * Unset keeps the original 2-decimal value without a sign (Overview tab).
   */
  percentDecimals?: number;
}

// Total Requests and % of Total columns: fixed widths and a wide gap, so the
// two right-aligned headers read as separate columns, not one phrase.
const TOTAL_COL_MIN_W = "104px";
const PCT_COL_MIN_W = "80px";
const COLUMN_GAP = 6;

const RankedShareList: React.FC<RankedShareListProps> = ({
  rows,
  headerLeft = METERING.SECTIONS.RANKED_SHARE.HEADER_LEFT,
  headerTaskType,
  headerTotal = METERING.SECTIONS.RANKED_SHARE.HEADER_TOTAL_REQUESTS,
  headerRight = METERING.SECTIONS.RANKED_SHARE.HEADER_RIGHT,
  tipTotal = METERING.SECTIONS.RANKED_SHARE.TOOLTIPS.TOTAL_REQUESTS,
  tipTaskType,
  tipRight = METERING.SECTIONS.RANKED_SHARE.TOOLTIPS.PCT_OF_TOTAL,
  variant = "default",
  percentDecimals,
}) => {
  const modelWithTaskType = variant === "modelWithTaskType" && Boolean(headerTaskType);
  const gridColumns = modelWithTaskType
    ? "minmax(0, 2fr) minmax(96px, 0.85fr) minmax(104px, 0.75fr) 80px"
    : "minmax(0, 2fr) minmax(104px, 0.75fr) 80px";

  const headerTotalCell = (
    <HStack spacing={1} justify="flex-end">
      <Text fontWeight="medium" textAlign="right">
        {replaceTenantCopy(headerTotal)}
      </Text>
      {tipTotal ? <InfoTip message={tipTotal} /> : null}
    </HStack>
  );

  const headerTaskTypeCell = headerTaskType ? (
    <HStack spacing={1}>
      <Text fontWeight="medium">{headerTaskType}</Text>
      {tipTaskType ? <InfoTip message={tipTaskType} /> : null}
    </HStack>
  ) : null;

  const headerRightCell = (
    <HStack spacing={1} justify="flex-end">
      <Text textAlign="right">{headerRight}</Text>
      {tipRight ? <InfoTip message={tipRight} /> : null}
    </HStack>
  );

  return (
    <VStack align="stretch" spacing={4} flex="1.5" w="full">
      {modelWithTaskType ? (
        <Grid
          templateColumns={gridColumns}
          columnGap={COLUMN_GAP}
          fontSize="xs"
          color="gray.500"
          px={1}
          alignItems="center"
        >
          <Text fontWeight="medium">{replaceTenantCopy(headerLeft)}</Text>
          {headerTaskTypeCell}
          {headerTotalCell}
          {headerRightCell}
        </Grid>
      ) : (
        <HStack justify="space-between" fontSize="xs" color="gray.500" px={1}>
          <HStack spacing={3} minW={0} flex="1">
            <Text fontWeight="medium">{replaceTenantCopy(headerLeft)}</Text>
            {headerTaskType ? (
              <Text fontWeight="medium" flexShrink={0}>
                {headerTaskType}
              </Text>
            ) : null}
          </HStack>
          <HStack spacing={COLUMN_GAP} flexShrink={0}>
            <Box minW={TOTAL_COL_MIN_W}>{headerTotalCell}</Box>
            <Box minW={PCT_COL_MIN_W}>{headerRightCell}</Box>
          </HStack>
        </HStack>
      )}

      {rows.map((row, i) => {
        const color = row.color ?? meteringColorAt(i);
        const modelCell = (
          <HStack spacing={2} minW={0}>
            <Text fontSize="xs" fontWeight="bold" color="gray.500" flexShrink={0}>
              #{row.rank}
            </Text>
            <Box w={2} h={2} borderRadius="full" bg={color} flexShrink={0} />
            <MeteringTableText flex={1} minW={0} maxW="unset">
              {row.label}
            </MeteringTableText>
          </HStack>
        );

        const totalCell = (
          <Text
            fontSize="sm"
            fontWeight="semibold"
            color="gray.700"
            minW={TOTAL_COL_MIN_W}
            textAlign="right"
            whiteSpace="nowrap"
          >
            {row.formattedValue}
          </Text>
        );

        const taskTypeCell = row.taskType ? (
          <TaskTypeLabel
            taskType={row.taskType}
            color={color}
            fontSize="sm"
            fontWeight="medium"
          />
        ) : row.subtitle ? (
          <Text fontSize="sm" color="gray.600" noOfLines={1}>
            {row.subtitle}
          </Text>
        ) : (
          <Text fontSize="sm" color="gray.400">
            {METERING.GRAPH.EMPTY_VALUE}
          </Text>
        );

        const pctCell = (
          <Text
            fontSize="sm"
            color="gray.500"
            textAlign="right"
            whiteSpace="nowrap"
            minW={PCT_COL_MIN_W}
          >
            {percentDecimals == null
              ? row.percentage.toFixed(2)
              : formatPercent(row.percentage, percentDecimals)}
          </Text>
        );

        if (modelWithTaskType) {
          return (
            <Box key={row.rank}>
              <Grid templateColumns={gridColumns} columnGap={COLUMN_GAP} alignItems="center" mb={1.5}>
                {modelCell}
                {taskTypeCell}
                <Box justifySelf="end">{totalCell}</Box>
                {pctCell}
              </Grid>
              <Grid templateColumns={gridColumns} columnGap={COLUMN_GAP}>
                <Progress
                  value={row.percentage}
                  size="sm"
                  borderRadius="full"
                  bg="gray.100"
                  sx={{ "& > div": { background: color } }}
                />
                <Box />
                <Box />
                <Box />
              </Grid>
            </Box>
          );
        }

        return (
          <Box key={row.rank}>
            <HStack justify="space-between" mb={1.5} spacing={3}>
              <HStack spacing={2} minW={0} flex="1">
                <Text fontSize="xs" fontWeight="bold" color="gray.500" flexShrink={0}>
                  #{row.rank}
                </Text>
                <Box w={2} h={2} borderRadius="full" bg={color} flexShrink={0} />
                <VStack align="flex-start" spacing={0} minW={0} flex="1">
                  <MeteringTableText flex={1} minW={0} maxW="unset">
                    {row.label}
                  </MeteringTableText>
                  {row.subtitle ? (
                    <Text fontSize="xs" color="gray.500" noOfLines={1}>
                      {row.subtitle}
                    </Text>
                  ) : null}
                </VStack>
              </HStack>
              <HStack spacing={COLUMN_GAP} flexShrink={0}>
                {totalCell}
                {pctCell}
              </HStack>
            </HStack>
            <Progress
              value={row.percentage}
              size="sm"
              borderRadius="full"
              bg="gray.100"
              sx={{ "& > div": { background: color } }}
            />
          </Box>
        );
      })}
    </VStack>
  );
};

export default RankedShareList;
