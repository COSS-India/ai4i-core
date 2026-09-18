import { HStack, IconButton, Tooltip } from "@chakra-ui/react";
import React from "react";
import type { DataTableColumn } from "./DataTable";

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
  icon: React.ReactElement;
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

const ACTION_HOVER: Record<string, { color: string; bg: string }> = {
  view: { color: "blue.500", bg: "blue.50" },
  edit: { color: "green.500", bg: "green.50" },
  delete: { color: "red.500", bg: "red.50" },
  download: { color: "blue.500", bg: "blue.50" },
  custom: { color: "blue.500", bg: "blue.50" },
};

export type DataTableActionsProps = {
  actions: DataTableAction[];
  spacing?: number;
  className?: string;
  /** Stop row-click propagation (default true). */
  stopPropagation?: boolean;
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
}: DataTableActionsProps) {
  const visible = actions.filter((a) => a.visible !== false);
  if (visible.length === 0) return null;

  return (
    <HStack
      spacing={spacing}
      className={className}
      onClick={stopPropagation ? (e) => e.stopPropagation() : undefined}
    >
      {visible.map((action) => {
        const hover = ACTION_HOVER[action.id] ?? ACTION_HOVER.custom;
        const color = action.color ?? "gray.700";
        const hoverColor = action.hoverColor ?? hover.color;
        const hoverBg = action.hoverBg ?? hover.bg;
        const tooltip = action.tooltip ?? action.label;
        const aria = action["aria-label"] ?? action.label;

        const button = (
          <IconButton
            aria-label={aria}
            icon={action.icon}
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
            {button}
          </Tooltip>
        );
      })}
    </HStack>
  );
}

export type CreateActionsColumnOptions<T> = {
  header?: React.ReactNode;
  id?: string;
  width?: string;
  minWidth?: string;
  align?: "left" | "center" | "right";
  getActions: (row: T, index: number) => DataTableAction[];
};

/** Builds a standard actions column that stops row-click propagation. */
export function createActionsColumn<T>(
  options: CreateActionsColumnOptions<T>,
): DataTableColumn<T> {
  const align = options.align ?? "left";
  return {
    id: options.id ?? "actions",
    header: options.header ?? "Actions",
    truncate: false,
    width: options.width,
    minWidth: options.minWidth ?? "120px",
    align,
    thProps: align !== "left" ? { textAlign: align } : undefined,
    tdProps: {
      textAlign: align !== "left" ? align : undefined,
      onClick: (e) => e.stopPropagation(),
    },
    cell: (row, index) => <DataTableActions actions={options.getActions(row, index)} />,
  };
}

export default DataTableActions;
