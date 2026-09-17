import { Badge, HStack, Text, Tooltip, VStack } from "@chakra-ui/react";
import React from "react";

export interface OverflowBadgeListProps {
  /** Labels to render, in display order. */
  items: readonly string[];
  /**
   * How many badges to render before collapsing the rest into `+N`.
   * A fixed count — not a fitted one — so the row is always a single line
   * regardless of how long the individual labels are.
   */
  visibleCount?: number;
  colorScheme?: string;
  /** Per-badge ceiling; a longer label ellipsises and keeps its own tooltip. */
  badgeMaxW?: string;
  emptyLabel?: string;
}

/**
 * A one-line badge list that collapses its tail into a `+N` badge, with the
 * hidden labels revealed on hover. Shared by the table columns that would
 * otherwise let a long list dictate the column's width (tiers, permissions,
 * roles, task types).
 */
export default function OverflowBadgeList({
  items,
  visibleCount = 2,
  colorScheme = "gray",
  badgeMaxW = "150px",
  emptyLabel = "—",
}: Readonly<OverflowBadgeListProps>) {
  if (items.length === 0) {
    return (
      <Text fontSize="sm" color="gray.400">
        {emptyLabel}
      </Text>
    );
  }

  const visible = items.slice(0, visibleCount);
  const hidden = items.slice(visibleCount);

  return (
    <HStack spacing={1} flexWrap="nowrap" overflow="hidden">
      {visible.map((label, i) => (
        <Tooltip
          key={`${label}-${i}`}
          label={label}
          placement="top"
          hasArrow
          openDelay={300}
        >
          <Badge
            colorScheme={colorScheme}
            fontSize="xs"
            px={2}
            py={0.5}
            maxW={badgeMaxW}
            isTruncated
            display="inline-block"
          >
            {label}
          </Badge>
        </Tooltip>
      ))}
      {hidden.length > 0 && (
        <Tooltip
          label={
            <VStack align="start" spacing={0}>
              {hidden.map((label, i) => (
                <Text key={`${label}-${i}`} fontSize="xs">
                  {label}
                </Text>
              ))}
            </VStack>
          }
          placement="top"
          hasArrow
          openDelay={200}
        >
          <Badge
            colorScheme="gray"
            fontSize="xs"
            px={2}
            py={0.5}
            flexShrink={0}
            cursor="default"
          >
            +{hidden.length}
          </Badge>
        </Tooltip>
      )}
    </HStack>
  );
}
