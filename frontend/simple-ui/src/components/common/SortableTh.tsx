import { Text } from "@chakra-ui/react";
import React from "react";
import { tableSortIndicator, type TableSortDirection } from "../../utils/tableSort";
import { ThWithTip } from "./InfoTip";

export interface SortableThProps {
  sortKey: string;
  activeSortKey: string;
  sortDirection: TableSortDirection;
  onSort: (key: string) => void;
  children: React.ReactNode;
  message?: string;
  isNumeric?: boolean;
  w?: string;
  minW?: string;
  sx?: Record<string, unknown>;
}

/** Clickable table header that toggles client-side sort on a column. */
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
        {tableSortIndicator(activeSortKey === sortKey, sortDirection)}
      </Text>
    </Text>
  </ThWithTip>
);

export default SortableTh;
