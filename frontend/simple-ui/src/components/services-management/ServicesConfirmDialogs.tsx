import React from "react";
import ConfirmDialog from "../common/ConfirmDialog";
import type { UseServicesManagementReturn } from "../../hooks/useServicesManagement";

export type ServicesConfirmDialogsProps = UseServicesManagementReturn;

export default function ServicesConfirmDialogs(sm: ServicesConfirmDialogsProps) {
  return (
    <>
      <ConfirmDialog
        isOpen={sm.isOpen}
        onClose={sm.onClose}
        onConfirm={sm.handleDeleteConfirm}
        title="Delete service"
        body={
          <>
            Are you sure you want to delete the service{" "}
            <strong>{sm.serviceToDelete?.name || sm.serviceToDelete?.service_id}</strong>?
            This action cannot be undone.
          </>
        }
        confirmLabel="Confirm"
        cancelLabel="Cancel"
        confirmColorScheme="red"
        isConfirmLoading={sm.deletingServiceUuid === sm.serviceToDelete?.serviceId}
        confirmLoadingText="Deleting..."
        leastDestructiveRef={sm.cancelRef}
      />

      <ConfirmDialog
        isOpen={sm.isPublishConfirmOpen}
        onClose={() => {
          sm.onPublishConfirmClose();
          sm.setConfirmPublishService(null);
        }}
        onConfirm={sm.handlePublishConfirm}
        title="Publish service"
        body={
          <>
            Are you sure you want to publish{" "}
            <strong>{sm.confirmPublishService?.name || sm.confirmPublishService?.serviceId}</strong>?
            The service will be available for use.
          </>
        }
        confirmLabel="Confirm"
        cancelLabel="Cancel"
        confirmColorScheme="green"
        isConfirmLoading={sm.publishingServiceUuid === sm.confirmPublishService?.serviceId}
        confirmLoadingText="Publishing..."
        leastDestructiveRef={sm.cancelPublishRef}
      />

      <ConfirmDialog
        isOpen={sm.isUnpublishConfirmOpen}
        onClose={() => {
          sm.onUnpublishConfirmClose();
          sm.setConfirmUnpublishService(null);
        }}
        onConfirm={sm.handleUnpublishConfirm}
        title="Unpublish service"
        body={
          <>
            Are you sure you want to unpublish{" "}
            <strong>{sm.confirmUnpublishService?.name || sm.confirmUnpublishService?.serviceId}</strong>?
            The service will no longer be available for use.
          </>
        }
        confirmLabel="Confirm"
        cancelLabel="Cancel"
        confirmColorScheme="red"
        isConfirmLoading={sm.unpublishingServiceUuid === sm.confirmUnpublishService?.serviceId}
        confirmLoadingText="Unpublishing..."
        leastDestructiveRef={sm.cancelUnpublishRef}
      />
    </>
  );
}
