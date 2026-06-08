import { Text, useToast } from "@chakra-ui/react";
import ConfirmDialog from "../common/ConfirmDialog";
import { usePoliciesPanel } from "./hooks/usePoliciesPanel";
import PoliciesTable from "./PoliciesTable";
import PolicyDetailModal from "./PolicyDetailModal";
import PolicyFormModal from "./PolicyFormModal";

export default function PoliciesPanel({ toast }: { toast: ReturnType<typeof useToast> }) {
  const p = usePoliciesPanel(toast);
  const {
    viewModal,
    viewPolicyId,
    closePolicyView,
    openEdit,
    requestDelete,
    modal,
    editingId,
    piiOptions,
    loadPiiOptions,
    reloadPolicies,
    confirmDeleteModal,
    deleteTarget,
    setDeleteTarget,
    deleting,
    handleConfirmDelete,
  } = p;

  return (
    <>
      <PoliciesTable {...p} />

      <PolicyDetailModal
        isOpen={viewModal.isOpen}
        onClose={closePolicyView}
        policyId={viewPolicyId}
        onEdit={(id) => {
          closePolicyView();
          openEdit(id);
        }}
        onDelete={(policy) => {
          closePolicyView();
          requestDelete(policy);
        }}
        onError={(msg) => toast({ title: msg, status: "error", duration: 5000, isClosable: true })}
      />

      <PolicyFormModal
        isOpen={modal.isOpen}
        onClose={modal.onClose}
        policyId={editingId}
        piiOptions={piiOptions}
        refreshPiiOptions={loadPiiOptions}
        onSaved={() => {
          modal.onClose();
          void reloadPolicies();
          void loadPiiOptions();
          toast({ title: "Saved", status: "success", duration: 2000 });
        }}
        onError={(msg) => toast({ title: msg, status: "error", duration: 5000, isClosable: true })}
      />

      <ConfirmDialog
        isOpen={confirmDeleteModal.isOpen}
        onClose={() => {
          confirmDeleteModal.onClose();
          if (!deleting) setDeleteTarget(null);
        }}
        title="Delete policy definition"
        body={
          deleteTarget ? (
            <Text>
              Delete <strong>{deleteTarget.name}</strong>? This action cannot be undone.
            </Text>
          ) : null
        }
        onConfirm={() => void handleConfirmDelete()}
        confirmLabel="Delete"
        confirmColorScheme="red"
        isConfirmLoading={deleting}
      />
    </>
  );
}
