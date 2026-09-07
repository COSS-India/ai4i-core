import { Badge, Box, Grid, HStack, Progress, Text, VStack } from "@chakra-ui/react";
import React from "react";
import { METERING } from "../../config/meteringConstants";
import { meteringColorAt } from "../../utils/meteringColors";
import { replaceTenantCopy } from "../../utils/replaceTenantCopy";
import InfoTip from "../common/InfoTip";
import MeteringTableText from "./MeteringTableText";
import { TaskTypeLabel } from "./UsageSpendCells";

export interface RankedShareRow {
  rank: number;
  label: string;
  /** Model task type shown as its own column (Model consumption list). */
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
  /** Donut list: Model Name, Model Task Type, Total requests, % of total. */
  variant?: "default" | "modelWithTaskType";
}

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
}) => {
  const modelWithTaskType = variant === "modelWithTaskType" && Boolean(headerTaskType);
  const gridColumns = modelWithTaskType
    ? "minmax(0, 2fr) minmax(96px, 0.85fr) minmax(88px, 0.75fr) 56px"
    : "minmax(0, 2fr) minmax(88px, 0.75fr) 56px";

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
          gap={3}
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
          <HStack spacing={2} flexShrink={0}>
            <Box minW="88px">{headerTotalCell}</Box>
            <Box minW="56px">{headerRightCell}</Box>
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
          <Badge
            colorScheme="gray"
            variant="subtle"
            fontSize="xs"
            borderRadius="md"
            fontWeight="semibold"
            minW="88px"
            textAlign="center"
            justifyContent="center"
          >
            {row.formattedValue}
          </Badge>
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
          >
            {row.percentage.toFixed(2)}
          </Text>
        );

        if (modelWithTaskType) {
          return (
            <Box key={row.rank}>
              <Grid templateColumns={gridColumns} gap={3} alignItems="center" mb={1.5}>
                {modelCell}
                {taskTypeCell}
                <Box justifySelf="end">{totalCell}</Box>
                {pctCell}
              </Grid>
              <Grid templateColumns={gridColumns} gap={3}>
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
              <HStack spacing={2} flexShrink={0}>
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
