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
    mandatoryHint="Name, Version, Task Type, Provider, and Actions stay visible. At least one other column must remain."
    canToggleOff={canToggleOffModelListColumn}
    toggle={toggleModelListColumn}
    onChange={onChange}
    onReset={onReset}
  />
);

export default ModelListColumnPicker;
