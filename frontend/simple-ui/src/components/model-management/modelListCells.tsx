import { Badge, Text } from "@chakra-ui/react";
import React from "react";
import {
  formatModelVersionStatusLabel,
  getTaskColorScheme,
  isModelVersionStatusActive,
} from "../../config/constants";
import { resolveTaskType } from "../../utils/platformService";
import { sortHeaderTrailingWidthPx } from "../common/TableControls";
import type { ModelDetails } from "../../types/platform";

/** Minimal row shape for list cells (matches Model Management table rows). */
export type ModelListCellModel = ModelDetails & {
  name: string;
  modelId?: string;
};

/**
 * Pinned widths for the short Model List columns, sized for the header text plus
 * its sort / info icon. No. of Services and Provider Name are sized to their
 * measured content instead (see CONTENT_WIDTH_IDS).
 */
const MODEL_LIST_FIXED_COLUMN_WIDTHS: Record<string, string> = {
  version: "7.5rem",
  taskType: "8.5rem",
  status: "8.5rem",
  createdAt: "10rem",
};

/** Content-sized, but a long provider name truncates (full name on hover) past this. */
const PROVIDER_NAME_MAX_WIDTH = "16rem";

/**
 * Spare table width is spread over the columns so no single gap opens up;
 * Model Name takes a double share. No. of Services stays at its content width
 * and Actions takes a share instead, so the right-aligned count and the
 * switch are not crowded together.
 */
const MODEL_LIST_COLUMN_GROW: Record<string, number> = {
  name: 2,
  version: 1,
  taskType: 1,
  providerName: 1,
  status: 1,
  createdAt: 1,
  actions: 2,
};

export function modelListColumnSizing(id: string): {
  width?: string;
  minWidth?: string;
  maxW?: string;
  grow?: number;
} {
  const grow = MODEL_LIST_COLUMN_GROW[id];
  if (id === "providerName") return { maxW: PROVIDER_NAME_MAX_WIDTH, grow };
  const width = MODEL_LIST_FIXED_COLUMN_WIDTHS[id];
  return width ? { width, minWidth: width, maxW: width, grow } : { grow };
}

function modelCreatedAtMs(model: {
  createdAt?: string | null;
  submittedOn?: number | null;
}): number {
  if (model.createdAt != null) return new Date(model.createdAt).getTime();
  if (model.submittedOn != null) return model.submittedOn * 1000;
  return Number.NaN;
}

export function renderModelNameCell(model: ModelListCellModel): React.ReactNode {
  const title = model.name || model.modelId;
  return (
    <Text
      fontWeight="medium"
      fontSize="sm"
      noOfLines={1}
      title={title}
    >
      {model.name || model.modelId || "—"}
    </Text>
  );
}

export function renderModelVersionCell(
  model: ModelListCellModel,
): React.ReactNode {
  return (
    <Text fontSize="sm" fontWeight="medium">
      {model.version || "1.0"}
    </Text>
  );
}

export function renderModelTaskTypeCell(
  model: ModelListCellModel,
): React.ReactNode {
  const taskType = resolveTaskType(model);
  return (
    <Badge colorScheme={getTaskColorScheme(taskType)} fontSize="xs">
      {taskType ? taskType.toUpperCase() : "N/A"}
    </Badge>
  );
}

export function renderModelProviderCell(
  model: ModelListCellModel,
): React.ReactNode {
  const label = (model.providerName ?? model.submitter?.name)?.trim() || "—";
  return (
    <Text
      fontSize="sm"
      color={label === "—" ? "ink.400" : "ink.700"}
      noOfLines={1}
      title={label}
    >
      {label}
    </Text>
  );
}

export function renderModelStatusCell(
  model: ModelListCellModel,
): React.ReactNode {
  return (
    <Badge
      colorScheme={
        isModelVersionStatusActive(model.versionStatus) ? "green" : "gray"
      }
      fontSize="xs"
    >
      {formatModelVersionStatusLabel(model.versionStatus)}
    </Badge>
  );
}

export function renderModelCreatedAtCell(
  model: ModelListCellModel,
): React.ReactNode {
  const createdMs = modelCreatedAtMs(model);
  return (
    <Text fontSize="sm" color="ink.600">
      {Number.isFinite(createdMs)
        ? new Date(createdMs).toLocaleDateString()
        : "N/A"}
    </Text>
  );
}

/** The row's own `noOfServices` (the API counts it when the column is requested). */
export function renderModelServiceCountCell(
  model: ModelListCellModel,
): React.ReactNode {
  const count = model.noOfServices ?? 0;
  return (
    <Text
      fontSize="sm"
      color="ink.600"
      // Right-aligned column: end under the header text, not its info + sort icons.
      pr={`${sortHeaderTrailingWidthPx(true)}px`}
      sx={{ fontVariantNumeric: "tabular-nums" }}
    >
      {count > 0 ? count : "-"}
    </Text>
  );
}

export { modelCreatedAtMs };
