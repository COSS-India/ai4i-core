import React from "react";
import { TriangleDownIcon, TriangleUpIcon } from "@chakra-ui/icons";
import {
  Button,
  HStack,
  IconButton,
  Select,
  Text,
  Tooltip,
  useColorModeValue,
} from "@chakra-ui/react";
import { FORM_LABEL_TO_INPUT_PT } from "./FormFieldsRow";
import InfoTip from "./InfoTip";

/** App-wide table — prefer importing from `./table` or `./DataTable`. */
export {
  DataTable as default,
  DataTable,
  TableSearchField,
  TableSelectField,
  DATA_TABLE_HEADER_SX,
  DATA_TABLE_CELL_MAX_W,
  type DataTableColumn,
  type DataTableProps,
} from "./DataTable";

export {
  useAdminDataTable,
  useAdminDataTableServer,
  DEFAULT_PAGE_SIZE_OPTIONS,
} from "../../hooks/useAdminDataTable";

/** Shared light/dark surface tokens for admin data tables (list pages, profile tabs, etc.). */
export function useAdminTableSurface() {
  const tableBg = useColorModeValue("white", "gray.800");
  const tableHeaderBg = useColorModeValue("gray.50", "gray.700");
  const tableRowHoverBg = useColorModeValue("gray.50", "gray.700");
  const cardBg = useColorModeValue("white", "gray.800");
  const borderColor = useColorModeValue("gray.200", "gray.700");
  return { tableBg, tableHeaderBg, tableRowHoverBg, cardBg, borderColor };
}

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
  /** When false, neither button is solid (inactive column). Default true. */
  active = true,
  hint,
}: {
  label: string;
  direction: SortDirection;
  onAsc: () => void;
  onDesc: () => void;
  ascAriaLabel: string;
  descAriaLabel: string;
  ascTooltipLabel?: string;
  descTooltipLabel?: string;
  active?: boolean;
  /** Optional circled-i tip beside the label. */
  hint?: string;
}) {
  const ascTooltip = ascTooltipLabel ?? `Sort ${label} ascending`;
  const descTooltip = descTooltipLabel ?? `Sort ${label} descending`;
  return (
    <HStack spacing={1.5}>
      <Text
        as="span"
        fontSize="11.5px"
        letterSpacing="0.05em"
        color="gray.500"
        textTransform="uppercase"
        fontWeight="bold"
      >
        {label}
      </Text>
      {hint ? <InfoTip message={hint} /> : null}
      <Tooltip label={ascTooltip} hasArrow>
        <IconButton
          aria-label={ascAriaLabel}
          icon={<TriangleUpIcon />}
          size="xs"
          variant={active && direction === "asc" ? "solid" : "ghost"}
          colorScheme="gray"
          onClick={onAsc}
        />
      </Tooltip>
      <Tooltip label={descTooltip} hasArrow>
        <IconButton
          aria-label={descAriaLabel}
          icon={<TriangleDownIcon />}
          size="xs"
          variant={active && direction === "desc" ? "solid" : "ghost"}
          colorScheme="gray"
          onClick={onDesc}
        />
      </Tooltip>
    </HStack>
  );
}

const PAGINATION_BTN_SX = {
  size: "sm" as const,
  variant: "ghost" as const,
  color: "gray.700",
  fontWeight: "medium" as const,
  borderRadius: "8px",
  px: 3,
  h: "32px",
  _hover: { bg: "gray.100", color: "gray.900" },
  _disabled: { opacity: 0.4, cursor: "not-allowed" },
};

/**
 * Existing pagination controls used by {@link DataTable}.
 * Logic/API unchanged — visual styles aligned with the DataTable shell.
 */
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
  borderColor = "gray.300",
  bg = "#FAFBFD",
  /**
   * - `attached` — flush footer/header inside the DataTable border shell (default for DataTable)
   * - `standalone` — spaced bar for rare external use
   */
  variant = "attached",
  /** Which edge of the table the bar sits on (controls divider side). */
  placement = "bottom",
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
  variant?: "attached" | "standalone";
  placement?: "top" | "bottom";
}) {
  const attached = variant === "attached";
  const edgeBorder =
    placement === "top"
      ? { borderBottomWidth: "1px" as const, borderTopWidth: 0 as const }
      : { borderTopWidth: "1px" as const, borderBottomWidth: 0 as const };

  return (
    <HStack
      mt={attached ? 0 : 4}
      px={4}
      py={3}
      justify="space-between"
      align="center"
      flexWrap="wrap"
      gap={3}
      bg={bg}
      borderColor={borderColor}
      {...edgeBorder}
      aria-label="Table pagination"
    >
      <Text fontSize="sm" color="gray.600" fontWeight="medium">
        {totalItems === 0 ? "No items" : `${startRow}–${endRow} of ${totalItems}`}
      </Text>
      <HStack spacing={3} align="center" flexWrap="wrap">
        <HStack spacing={2} align="center">
          <Text
            fontSize="11.5px"
            letterSpacing="0.04em"
            color="gray.500"
            textTransform="uppercase"
            fontWeight="bold"
            whiteSpace="nowrap"
          >
            Rows per page
          </Text>
          <Select
            size="sm"
            w="72px"
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            bg="white"
            borderColor="gray.300"
            borderRadius="8px"
            h="32px"
            aria-label="Rows per page"
          >
            {pageSizeOptions.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </Select>
        </HStack>
        <HStack
          spacing={0.5}
          align="center"
          borderWidth="1px"
          borderColor="gray.300"
          borderRadius="10px"
          bg="white"
          p="2px"
        >
          <Button {...PAGINATION_BTN_SX} onClick={onFirst} isDisabled={!canPrev} aria-label="First page">
            First
          </Button>
          <Button {...PAGINATION_BTN_SX} onClick={onPrev} isDisabled={!canPrev} aria-label="Previous page">
            Previous
          </Button>
          <Text
            fontSize="sm"
            color="gray.700"
            fontWeight="semibold"
            px={3}
            minW="7.5rem"
            textAlign="center"
            userSelect="none"
          >
            Page {page} of {totalPages}
          </Text>
          <Button {...PAGINATION_BTN_SX} onClick={onNext} isDisabled={!canNext} aria-label="Next page">
            Next
          </Button>
          <Button {...PAGINATION_BTN_SX} onClick={onLast} isDisabled={!canNext} aria-label="Last page">
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
  align = "flex-start",
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
  const actions =
    (hasActiveFilters && onClear) || rightContent ? (
      <HStack
        spacing={2}
        pt={FORM_LABEL_TO_INPUT_PT}
        align="center"
        flexShrink={0}
        ml={rightContent ? "auto" : undefined}
      >
        {hasActiveFilters && onClear ? (
          <Button size="sm" variant="outline" onClick={onClear}>
            {clearLabel}
          </Button>
        ) : null}
        {rightContent}
      </HStack>
    ) : null;

  return (
    <HStack
      spacing={spacing}
      align={align}
      justify={justify}
      flexWrap="wrap"
      rowGap={3}
      w="100%"
    >
      {children}
      {actions}
    </HStack>
  );
}
