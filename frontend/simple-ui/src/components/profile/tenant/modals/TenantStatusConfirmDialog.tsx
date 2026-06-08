import ConfirmDialog from "../../../common/ConfirmDialog";
import { formatStatusConfirmLabel } from "../utils";
import type { TenantTabContext } from "../types";

type Props = TenantTabContext;

export default function TenantStatusConfirmDialog({ tm }: Props) {
  const target = tm.statusUpdateTarget;
  const isOpen = tm.isStatusDialogOpen && Boolean(target);
  const targetLabel = target?.type === "tenant" ? "tenant" : "user";
  const statusLabel = formatStatusConfirmLabel(target?.type, tm.statusUpdateNewStatus);
  return (
    <ConfirmDialog
      isOpen={isOpen}
      onClose={tm.closeStatusDialog}
      onConfirm={tm.handleConfirmStatusUpdate}
      title={`Change ${targetLabel} status`}
      body={`Set ${targetLabel} status to "${statusLabel}"?`}
      confirmLabel="Update"
      confirmColorScheme="blue"
      isConfirmLoading={tm.isSubmittingStatus}
    />
  );
}
