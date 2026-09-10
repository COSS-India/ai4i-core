import React from "react";
import {
  Box,
  Button,
  HStack,
  Select,
  Text,
  Tooltip,
  useColorModeValue,
} from "@chakra-ui/react";
import { FORM_LABEL_TO_INPUT_PT } from "./FormFieldsRow";
import InfoTip from "./InfoTip";

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

/** Compact up caret used in table sort controls. */
function CaretUpIcon({ size = 10 }: { size?: number }) {
  return (
    <Box as="svg" viewBox="0 0 10 6" w={`${size}px`} h={`${size * 0.6}px`} fill="currentColor" aria-hidden>
      <path d="M5 0.5L9.5 5.5H0.5L5 0.5Z" />
    </Box>
  );
}

/** Compact down caret used in table sort controls. */
function CaretDownIcon({ size = 10 }: { size?: number }) {
  return (
    <Box as="svg" viewBox="0 0 10 6" w={`${size}px`} h={`${size * 0.6}px`} fill="currentColor" aria-hidden>
      <path d="M5 5.5L0.5 0.5H9.5L5 5.5Z" />
    </Box>
  );
}

function SortCaretButton({
  direction,
  isActive,
  label,
  tooltip,
  onClick,
}: {
  direction: SortDirection;
  isActive: boolean;
  label: string;
  tooltip: string;
  onClick: () => void;
}) {
  return (
    <Tooltip label={tooltip} hasArrow openDelay={250}>
      <Box
        as="button"
        type="button"
        aria-label={label}
        aria-pressed={isActive}
        onClick={(e: React.MouseEvent) => {
          e.stopPropagation();
          onClick();
        }}
        display="flex"
        alignItems="center"
        justifyContent="center"
        w="14px"
        h="9px"
        p={0}
        m={0}
        border="none"
        bg="transparent"
        cursor="pointer"
        color={isActive ? "blue.500" : "gray.300"}
        _hover={{ color: isActive ? "blue.600" : "gray.500" }}
        _focusVisible={{
          outline: "2px solid",
          outlineColor: "blue.300",
          outlineOffset: "1px",
          borderRadius: "2px",
        }}
        transition="color 0.12s ease"
        lineHeight={0}
      >
        {direction === "asc" ? <CaretUpIcon /> : <CaretDownIcon />}
      </Box>
    </Tooltip>
  );
}

/**
 * Column header with optional hint and a compact stacked asc/desc caret control.
 * Inactive columns show muted dual carets; the active direction uses a blue caret.
 */
export function TableSortHeader({
  label,
  direction,
  onAsc,
  onDesc,
  ascAriaLabel,
  descAriaLabel,
  ascTooltipLabel,
  descTooltipLabel,
  /** When false, neither caret is emphasized (inactive column). Default true. */
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
  const ascActive = active && direction === "asc";
  const descActive = active && direction === "desc";

  return (
    <HStack spacing={1.5} align="center">
      <Text
        as="span"
        fontSize="11.5px"
        letterSpacing="0.05em"
        color={active ? "gray.700" : "gray.500"}
        textTransform="uppercase"
        fontWeight="bold"
      >
        {label}
      </Text>
      {hint ? <InfoTip message={hint} /> : null}
      <Box
        as="span"
        display="inline-flex"
        flexDirection="column"
        alignItems="center"
        justifyContent="center"
        gap="1px"
        px="2px"
        py="1px"
        borderRadius="4px"
        bg={active ? "blue.50" : "transparent"}
        _groupHover={{ bg: "gray.100" }}
        transition="background 0.12s ease"
        aria-hidden={false}
      >
        <SortCaretButton
          direction="asc"
          isActive={ascActive}
          label={ascAriaLabel}
          tooltip={ascTooltip}
          onClick={onAsc}
        />
        <SortCaretButton
          direction="desc"
          isActive={descActive}
          label={descAriaLabel}
          tooltip={descTooltip}
          onClick={onDesc}
        />
      </Box>
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
