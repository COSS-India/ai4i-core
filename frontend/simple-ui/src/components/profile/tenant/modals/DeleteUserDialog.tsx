import ConfirmDialog from "../../../common/ConfirmDialog";
import type { TenantTabContext } from "../types";

type Props = TenantTabContext;

export default function DeleteUserDialog({ tm }: Props) {
  const target = tm.deleteUserTarget;
  return (
    <ConfirmDialog
      isOpen={tm.isDeleteUserDialogOpen}
      onClose={tm.closeDeleteUserDialog}
      onConfirm={tm.handleConfirmDeleteUser}
      title="Delete user"
      body={`Soft-delete user ${target?.username ?? ""}?`}
      confirmLabel="Delete"
      confirmColorScheme="red"
      isConfirmLoading={tm.isDeletingUser}
    />
  );
}
