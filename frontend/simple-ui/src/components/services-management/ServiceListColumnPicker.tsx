import React from "react";
import { FIELD_HINTS } from "../../config/fieldHints";
import AdminListColumnPicker from "../common/AdminListColumnPicker";
import {
  SERVICE_LIST_COLUMNS,
  canToggleOffServiceListColumn,
  toggleServiceListColumn,
  type ServiceListColumnDef,
} from "./serviceListColumns";

type ServiceListColumnPickerProps = {
  columns?: readonly ServiceListColumnDef[];
  visibleIds: readonly string[];
  onChange: (next: string[]) => void;
  onReset: () => void;
};

const ServiceListColumnPicker: React.FC<
  Readonly<ServiceListColumnPickerProps>
> = ({
  columns = SERVICE_LIST_COLUMNS,
  visibleIds,
  onChange,
  onReset,
}) => (
  <AdminListColumnPicker
    columns={columns}
    visibleIds={visibleIds}
    helper={FIELD_HINTS.service.columns.tip}
    mandatoryHint="Name and Actions stay visible. At least one other column must remain."
    canToggleOff={canToggleOffServiceListColumn}
    toggle={toggleServiceListColumn}
    onChange={onChange}
    onReset={onReset}
  />
);

export default ServiceListColumnPicker;
