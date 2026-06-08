import React from "react";
import ConfirmDialog from "../common/ConfirmDialog";
import type { UseModelManagementReturn } from "../../hooks/useModelManagement";

export function ModelConfirmDialog(props: UseModelManagementReturn) {
  const {
    isConfirmOpen,
    closeConfirmDialog,
    handleConfirmAction,
    confirmAction,
    modelToConfirm,
    updatingModelId,
    cancelConfirmRef,
  } = props;

  return (
    <ConfirmDialog
      isOpen={isConfirmOpen}
      onClose={closeConfirmDialog}
      onConfirm={handleConfirmAction}
      title={confirmAction === "deprecate" ? "Deprecate model" : "Activate model"}
      body={
        confirmAction === "deprecate" ? (
          <>
            Are you sure you want to deprecate{" "}
            <strong>{modelToConfirm?.name || modelToConfirm?.modelId}</strong>?
            Deprecated models cannot be used for new services.
          </>
        ) : (
          <>
            Are you sure you want to activate{" "}
            <strong>{modelToConfirm?.name || modelToConfirm?.modelId}</strong>?
            The model will be available for services again.
          </>
        )
      }
      confirmLabel="Confirm"
      cancelLabel="Cancel"
      confirmColorScheme={confirmAction === "deprecate" ? "orange" : "green"}
      isConfirmLoading={updatingModelId === modelToConfirm?.modelId}
      confirmLoadingText={confirmAction === "deprecate" ? "Deprecating..." : "Activating..."}
      leastDestructiveRef={cancelConfirmRef}
    />
  );
}
