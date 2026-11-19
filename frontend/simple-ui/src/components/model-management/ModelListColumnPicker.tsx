import React from "react";
import { FIELD_HINTS } from "../../config/fieldHints";
import AdminListColumnPicker from "../common/AdminListColumnPicker";
import {
  MODEL_LIST_COLUMNS,
  canToggleOffModelListColumn,
  toggleModelListColumn,
  type ModelListColumnDef,
} from "./modelListColumns";

type ModelListColumnPickerProps = {
  columns?: readonly ModelListColumnDef[];
  visibleIds: readonly string[];
  onChange: (next: string[]) => void;
  onReset: () => void;
};

function mandatoryColumnsHint(columns: readonly ModelListColumnDef[]): string {
  const labels = columns.filter((column) => column.mandatory).map((column) => column.label);
  if (labels.length === 0) return "";
  if (labels.length === 1) return `${labels[0]} stays visible.`;
  if (labels.length === 2) return `${labels[0]} and ${labels[1]} stay visible.`;
  return `${labels.slice(0, -1).join(", ")}, and ${labels.at(-1)} stay visible.`;
}

const ModelListColumnPicker: React.FC<
  Readonly<ModelListColumnPickerProps>
> = ({
  columns = MODEL_LIST_COLUMNS,
  visibleIds,
  onChange,
  onReset,
}) => (
  <AdminListColumnPicker
    columns={columns}
    visibleIds={visibleIds}
    helper={FIELD_HINTS.model.columns.tip}
    mandatoryHint={mandatoryColumnsHint(columns)}
    canToggleOff={canToggleOffModelListColumn}
    toggle={toggleModelListColumn}
    onChange={onChange}
    onReset={onReset}
  />
);

export default ModelListColumnPicker;
