import { Text, useToast } from "@chakra-ui/react";
import ConfirmDialog from "../common/ConfirmDialog";
import { usePiiTypesPanel } from "./hooks/usePiiTypesPanel";
import PiiTypeDetailModal from "./PiiTypeDetailModal";
import PiiTypeFormModal from "./PiiTypeFormModal";
import PiiTypesTable from "./PiiTypesTable";

export default function PiiTypesPanel({ toast }: { toast: ReturnType<typeof useToast> }) {
  const p = usePiiTypesPanel(toast);
  const {
    viewModal,
    viewPiiId,
    closePiiView,
    openEdit,
    modal,
    editing,
    label,
    setLabel,
    regex,
    setRegex,
    examples,
    setExamples,
    mask,
    setMask,
    saving,
    piiDetailLoading,
    save,
    confirmDel,
    deleteTarget,
    deleting,
    confirmDelete,
  } = p;

  return (
    <>
      <PiiTypesTable {...p} />

      <PiiTypeDetailModal
        isOpen={viewModal.isOpen}
        onClose={closePiiView}
        piiTypeId={viewPiiId}
        onEdit={(row) => {
          closePiiView();
          openEdit(row);
        }}
        onError={(msg) => toast({ title: msg, status: "error", duration: 5000, isClosable: true })}
      />

      <PiiTypeFormModal
        isOpen={modal.isOpen}
        onClose={modal.onClose}
        editing={editing}
        label={label}
        setLabel={setLabel}
        regex={regex}
        setRegex={setRegex}
        examples={examples}
        setExamples={setExamples}
        mask={mask}
        setMask={setMask}
        saving={saving}
        piiDetailLoading={piiDetailLoading}
        onSave={() => void save()}
      />

      <ConfirmDialog
        isOpen={confirmDel.isOpen}
        onClose={confirmDel.onClose}
        title="Delete PII type"
        body={
          deleteTarget ? (
            <Text>
              Remove <strong>{deleteTarget.pii_type_label}</strong>? Policies referencing it may fail to
              update.
            </Text>
          ) : null
        }
        onConfirm={() => void confirmDelete()}
        confirmLabel="Delete"
        confirmColorScheme="red"
        isConfirmLoading={deleting}
      />
    </>
  );
}
