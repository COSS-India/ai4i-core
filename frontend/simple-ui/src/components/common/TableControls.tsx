import React from "react";
import { Button, HStack, IconButton, Select, Text, Tooltip } from "@chakra-ui/react";
import { TriangleDownIcon, TriangleUpIcon } from "@chakra-ui/icons";

type SortDirection = "asc" | "desc";

export function TableSortHeader({
  label,
  direction,
  onAsc,
  onDesc,
  ascAriaLabel,
  descAriaLabel,
  ascTooltipLabel,
  descTooltipLabel,
}: {
  label: string;
  direction: SortDirection;
  onAsc: () => void;
  onDesc: () => void;
  ascAriaLabel: string;
  descAriaLabel: string;
  ascTooltipLabel?: string;
  descTooltipLabel?: string;
}) {
  const ascTooltip = ascTooltipLabel ?? `Sort ${label} ascending`;
  const descTooltip = descTooltipLabel ?? `Sort ${label} descending`;
  return (
    <HStack spacing={2}>
      <Text>{label}</Text>
      <Tooltip label={ascTooltip} hasArrow>
        <IconButton
          aria-label={ascAriaLabel}
          icon={<TriangleUpIcon />}
          size="xs"
          variant={direction === "asc" ? "solid" : "ghost"}
          colorScheme="gray"
          onClick={onAsc}
        />
      </Tooltip>
      <Tooltip label={descTooltip} hasArrow>
        <IconButton
          aria-label={descAriaLabel}
          icon={<TriangleDownIcon />}
          size="xs"
          variant={direction === "desc" ? "solid" : "ghost"}
          colorScheme="gray"
          onClick={onDesc}
        />
      </Tooltip>
    </HStack>
  );
}

export function TablePaginationBar({
  startRow,
  endRow,
  totalItems,
  page,
  totalPages,
  pageSize,
  pageSizeOptions,
  onPageSizeChange,
  onFirst,
  onPrev,
  onNext,
  onLast,
  canPrev,
  canNext,
  borderColor = "gray.200",
  bg = "white",
}: {
  startRow: number;
  endRow: number;
  totalItems: number;
  page: number;
  totalPages: number;
  pageSize: number;
  pageSizeOptions: number[];
  onPageSizeChange: (value: number) => void;
  onFirst: () => void;
  onPrev: () => void;
  onNext: () => void;
  onLast: () => void;
  canPrev: boolean;
  canNext: boolean;
  borderColor?: string;
  bg?: string;
}) {
  return (
    <HStack
      mt={4}
      justify="space-between"
      align="center"
      flexWrap="wrap"
      gap={2}
      borderTopWidth="1px"
      borderColor={borderColor}
      pt={4}
    >
      <Text fontSize="sm" color="gray.600">
        {totalItems === 0 ? "No items" : `${startRow}–${endRow} of ${totalItems}`}
      </Text>
      <HStack spacing={2} align="center" flexWrap="wrap">
        <Text fontSize="sm" color="gray.600" whiteSpace="nowrap">
          Rows per page
        </Text>
        <Select
          size="sm"
          w="70px"
          value={pageSize}
          onChange={(e) => onPageSizeChange(Number(e.target.value))}
          bg={bg}
        >
          {pageSizeOptions.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </Select>
        <HStack spacing={1}>
          <Button size="sm" variant="outline" onClick={onFirst} isDisabled={!canPrev} aria-label="First page">
            First
          </Button>
          <Button size="sm" variant="outline" onClick={onPrev} isDisabled={!canPrev} aria-label="Previous page">
            Previous
          </Button>
          <Text fontSize="sm" color="gray.600" px={2}>
            Page {page} of {totalPages}
          </Text>
          <Button size="sm" variant="outline" onClick={onNext} isDisabled={!canNext} aria-label="Next page">
            Next
          </Button>
          <Button size="sm" variant="outline" onClick={onLast} isDisabled={!canNext} aria-label="Last page">
            Last
          </Button>
        </HStack>
      </HStack>
    </HStack>
  );
}

export function TableFilterToolbar({
  children,
  hasActiveFilters,
  onClear,
  clearLabel = "Clear all",
  rightContent,
  spacing = 3,
  align = "center",
  justify = "flex-start",
}: {
  children: React.ReactNode;
  hasActiveFilters?: boolean;
  onClear?: () => void;
  clearLabel?: string;
  rightContent?: React.ReactNode;
  spacing?: number;
  align?: string;
  justify?: string;
}) {
  return (
    <HStack spacing={spacing} align={align} justify={justify} flexWrap="wrap" rowGap={3} w="100%">
      {children}
      {hasActiveFilters && onClear ? (
        <Button size="sm" variant="outline" onClick={onClear}>
          {clearLabel}
        </Button>
      ) : null}
      {rightContent}
    </HStack>
  );
}
