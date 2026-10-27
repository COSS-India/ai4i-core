import { Box, HStack, IconButton, Tooltip } from "@chakra-ui/react";
import { DeleteIcon, DownloadIcon, EditIcon, ViewIcon } from "@chakra-ui/icons";
import React from "react";
import type { DataTableColumn } from "./DataTable";
import { ADMIN_ACTIONS_COLUMN_WIDTH } from "./dataTableUtils";

export type DataTableActionId =
  | "view"
  | "edit"
  | "delete"
  | "download"
  | "custom"
  | (string & {});

export type DataTableAction = {
  id: DataTableActionId;
  /** Accessible name and default tooltip. */
  label: string;
  icon?: React.ReactElement;
  onClick: () => void;
  /** When false, the action is hidden. Default true. */
  visible?: boolean;
  disabled?: boolean;
  isLoading?: boolean;
  tooltip?: string;
  /** IconButton color when idle. */
  color?: string;
  /** Hover color / background pair. */
  hoverColor?: string;
  hoverBg?: string;
  "aria-label"?: string;
};

const DEFAULT_ICONS: Record<string, React.ReactElement> = {
  view: <ViewIcon />,
  edit: <EditIcon />,
  delete: <DeleteIcon />,
  download: <DownloadIcon />,
};

const ACTION_HOVER: Record<string, { color: string; bg: string }> = {
  view: { color: "ink.700", bg: "ink.50" },
  edit: { color: "ink.700", bg: "ink.50" },
  delete: { color: "red.500", bg: "red.50" },
  download: { color: "ink.700", bg: "ink.50" },
  custom: { color: "ink.700", bg: "ink.50" },
};

export type DataTableActionsProps = {
  actions: DataTableAction[];
  spacing?: number;
  className?: string;
  /** Stop row-click propagation (default true). */
  stopPropagation?: boolean;
  justify?: "flex-start" | "flex-end" | "center";
};

/**
 * Renders a row’s action IconButtons from configuration.
 * Hidden when `visible === false`; tooltips respect disabled state.
 */
export function DataTableActions({
  actions,
  spacing = 1,
  className = "row-actions",
  stopPropagation = true,
  justify,
}: DataTableActionsProps) {
  const visible = actions.filter((a) => a.visible !== false);
  if (visible.length === 0) return null;

  return (
    <HStack
      spacing={spacing}
      justify={justify}
      w={justify ? "full" : undefined}
      className={className}
      onClick={stopPropagation ? (e) => e.stopPropagation() : undefined}
    >
      {visible.map((action) => {
        const hover = ACTION_HOVER[action.id] ?? ACTION_HOVER.custom;
        const color = action.color ?? "ink.600";
        const hoverColor = action.hoverColor ?? hover.color;
        const hoverBg = action.hoverBg ?? hover.bg;
        const tooltip = action.tooltip ?? action.label;
        const aria = action["aria-label"] ?? action.label;
        const icon = action.icon ?? DEFAULT_ICONS[action.id];
        if (!icon) return null;

        const button = (
          <IconButton
            aria-label={aria}
            icon={icon}
            size="sm"
            variant="ghost"
            color={color}
            isDisabled={action.disabled}
            isLoading={action.isLoading}
            _hover={{ color: hoverColor, bg: hoverBg }}
            onClick={(e) => {
              if (stopPropagation) e.stopPropagation();
              action.onClick();
            }}
          />
        );

        return (
          <Tooltip key={action.id} label={tooltip} hasArrow openDelay={300} isDisabled={!tooltip}>
            {action.disabled ? (
              <Box
                as="span"
                display="inline-flex"
                tabIndex={0}
                aria-label={aria}
                borderRadius="md"
                _focusVisible={{ boxShadow: "outline" }}
              >
                {button}
              </Box>
            ) : (
              button
            )}
          </Tooltip>
        );
      })}
    </HStack>
  );
}

/** Compact Actions width under `table-layout: fixed` (fits ~3–4 icon buttons). */
export const DATA_TABLE_ACTIONS_COLUMN_WIDTH = ADMIN_ACTIONS_COLUMN_WIDTH;

export type CreateActionsColumnOptions<T> = {
  header?: React.ReactNode;
  id?: string;
  width?: string;
  minWidth?: string;
  maxW?: string;
  align?: "left" | "center" | "right";
  getActions: (row: T, index: number) => DataTableAction[];
};

function resolveActionsJustify(
  align: "left" | "center" | "right",
): "flex-start" | "flex-end" | "center" | undefined {
  if (align === "right") return "flex-end";
  if (align === "center") return "center";
  return undefined;
}

/** Builds a standard actions column that stops row-click propagation. */
export function createActionsColumn<T>(
  options: CreateActionsColumnOptions<T>,
): DataTableColumn<T> {
  const align = options.align ?? "right";
  const width = options.width ?? DATA_TABLE_ACTIONS_COLUMN_WIDTH;
  const justify = resolveActionsJustify(align);
  return {
    id: options.id ?? "actions",
    header: options.header ?? "Actions",
    truncate: false,
    width,
    minWidth: options.minWidth ?? width,
    maxW: options.maxW ?? width,
    align,
    thProps: {
      textAlign: align,
      whiteSpace: "nowrap",
      px: 2,
    },
    tdProps: {
      textAlign: align,
      whiteSpace: "nowrap",
      px: 2,
      onClick: (e) => e.stopPropagation(),
    },
    cell: (row, index) => (
      <DataTableActions justify={justify} actions={options.getActions(row, index)} />
    ),
  };
}

export default DataTableActions;
