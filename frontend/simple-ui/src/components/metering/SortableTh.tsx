import { Text } from "@chakra-ui/react";
import React from "react";
import { ThWithTip } from "../common/InfoTip";
import type { MeteringSortDirection } from "../../utils/meteringTableSort";
import { sortIndicator } from "../../utils/meteringTableSort";

interface SortableThProps {
  sortKey: string;
  activeSortKey: string;
  sortDirection: MeteringSortDirection;
  onSort: (key: string) => void;
  children: React.ReactNode;
  message?: string;
  isNumeric?: boolean;
  w?: string;
  minW?: string;
  sx?: Record<string, unknown>;
}

/** Sortable metering table header — click toggles asc/desc on that column. */
export const SortableTh: React.FC<SortableThProps> = ({
  sortKey,
  activeSortKey,
  sortDirection,
  onSort,
  children,
  message,
  isNumeric,
  w,
  minW,
  sx,
}) => (
  <ThWithTip
    message={message}
    isNumeric={isNumeric}
    w={w}
    minW={minW}
    sx={sx}
    cursor="pointer"
    userSelect="none"
    onClick={() => onSort(sortKey)}
  >
    <Text as="span">
      {children}{" "}
      <Text as="span" fontSize="10px" color="gray.400">
        {sortIndicator(activeSortKey === sortKey, sortDirection)}
      </Text>
    </Text>
  </ThWithTip>
);

export default SortableTh;
