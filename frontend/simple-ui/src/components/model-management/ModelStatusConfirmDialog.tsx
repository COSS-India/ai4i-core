import React, { type RefObject } from "react";
import ConfirmDialog from "../common/ConfirmDialog";

export type ModelStatusAction = "deprecate" | "activate";

type ModelStatusConfirmDialogProps = {
  isOpen: boolean;
  action: ModelStatusAction | null;
  model: { name?: string; modelId?: string } | null;
  isConfirmLoading: boolean;
  onClose: () => void;
  onConfirm: () => void | Promise<void>;
  leastDestructiveRef?: RefObject<HTMLButtonElement>;
};

const COPY: Record<
  ModelStatusAction,
  { title: string; verb: string; outcome: string; color: string; loading: string }
> = {
  deprecate: {
    title: "Deprecate model",
    verb: "deprecate",
    outcome: "Deprecated models cannot be used for new services.",
    color: "orange",
    loading: "Deprecating...",
  },
  activate: {
    title: "Activate model",
    verb: "activate",
    outcome: "The model will be available for services again.",
    color: "green",
    loading: "Activating...",
  },
};

/** Confirm before deprecating or activating a model version. */
const ModelStatusConfirmDialog: React.FC<Readonly<ModelStatusConfirmDialogProps>> = ({
  isOpen,
  action,
  model,
  isConfirmLoading,
  onClose,
  onConfirm,
  leastDestructiveRef,
}) => {
  // No action yet (dialog closing) → keep the activate copy, as before.
  const copy = COPY[action ?? "activate"];
  return (
    <ConfirmDialog
      isOpen={isOpen}
      onClose={onClose}
      onConfirm={onConfirm}
      title={copy.title}
      body={
        <>
          Are you sure you want to {copy.verb}{" "}
          <strong>{model?.name || model?.modelId}</strong>? {copy.outcome}
        </>
      }
      confirmLabel="Confirm"
      cancelLabel="Cancel"
      confirmColorScheme={copy.color}
      isConfirmLoading={isConfirmLoading}
      confirmLoadingText={copy.loading}
      leastDestructiveRef={leastDestructiveRef}
    />
  );
};

export default ModelStatusConfirmDialog;
