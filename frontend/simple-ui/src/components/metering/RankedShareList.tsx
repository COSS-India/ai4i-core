import { Badge, Box, HStack, Progress, Text, VStack } from "@chakra-ui/react";
import React from "react";
import { METERING } from "../../config/meteringConstants";
import { meteringColorAt } from "../../utils/meteringColors";
import { replaceTenantCopy } from "../../utils/replaceTenantCopy";
import { MeteringInfoTip } from "./MeteringInfoTip";
import MeteringTableText from "./MeteringTableText";

export interface RankedShareRow {
  rank: number;
  label: string;
  formattedValue: string;
  percentage: number;
}

interface RankedShareListProps {
  rows: RankedShareRow[];
  headerLeft?: string;
  headerTotal?: string;
  headerRight?: string;
  tipTotal?: string;
  tipRight?: string;
}

const RankedShareList: React.FC<RankedShareListProps> = ({
  rows,
  headerLeft = METERING.SECTIONS.RANKED_SHARE.HEADER_LEFT,
  headerTotal = METERING.SECTIONS.RANKED_SHARE.HEADER_TOTAL_REQUESTS,
  headerRight = METERING.SECTIONS.RANKED_SHARE.HEADER_RIGHT,
  tipTotal = METERING.SECTIONS.RANKED_SHARE.TOOLTIPS.TOTAL_REQUESTS,
  tipRight = METERING.SECTIONS.RANKED_SHARE.TOOLTIPS.PCT_OF_TOTAL,
}) => (
  <VStack align="stretch" spacing={4} flex="1.5" w="full">
    <HStack justify="space-between" fontSize="xs" color="gray.500" px={1}>
      <Text fontWeight="medium">{replaceTenantCopy(headerLeft)}</Text>
      <HStack spacing={2} flexShrink={0}>
        <HStack spacing={1} minW="88px" justify="flex-end">
          <Text fontWeight="medium" textAlign="right">
            {replaceTenantCopy(headerTotal)}
          </Text>
          {tipTotal ? <MeteringInfoTip label={headerTotal} tip={tipTotal} boxSize={3} /> : null}
        </HStack>
        <HStack spacing={1} minW="56px" justify="flex-end">
          <Text textAlign="right">{headerRight}</Text>
          {tipRight ? <MeteringInfoTip label={headerRight} tip={tipRight} boxSize={3} /> : null}
        </HStack>
      </HStack>
    </HStack>
    {rows.map((row, i) => {
      const color = meteringColorAt(i);
      return (
        <Box key={row.rank}>
          <HStack justify="space-between" mb={1.5} spacing={3}>
            <HStack spacing={2} minW={0} flex="1">
              <Text fontSize="xs" fontWeight="bold" color="gray.500" flexShrink={0}>
                #{row.rank}
              </Text>
              <Box w={2} h={2} borderRadius="full" bg={color} flexShrink={0} />
              <MeteringTableText flex={1} minW={0} maxW="unset">
                {row.label}
              </MeteringTableText>
            </HStack>
            <HStack spacing={2} flexShrink={0}>
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
              <Text
                fontSize="sm"
                color="gray.500"
                minW="56px"
                textAlign="right"
                whiteSpace="nowrap"
                flexShrink={0}
              >
                {row.percentage.toFixed(2)}%
              </Text>
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

export default RankedShareList;
