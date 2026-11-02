import { Badge, Text } from "@chakra-ui/react";
import React from "react";
import {
  formatModelVersionStatusLabel,
  getTaskColorScheme,
  isModelVersionStatusActive,
} from "../../config/constants";
import { resolveTaskType } from "../../utils/platformService";
import type { ModelDetails } from "../../types/platform";

/** Minimal row shape for list cells (matches Model Management table rows). */
export type ModelListCellModel = ModelDetails & {
  name: string;
  modelId?: string;
};

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
  const label = model.submitter?.name?.trim() || "—";
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

export { modelCreatedAtMs };
