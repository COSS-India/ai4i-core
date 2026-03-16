import React, { ReactNode, RefObject } from "react";
import {
  AlertDialog,
  AlertDialogBody,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogOverlay,
  Button,
  useColorModeValue,
} from "@chakra-ui/react";

export interface ConfirmDialogProps {
  /** Whether the dialog is visible. */
  isOpen: boolean;
  /** Called when the dialog should be closed (either Cancel or overlay/ESC). */
  onClose: () => void;
  /** Called when the user confirms the action. */
  onConfirm: () => void | Promise<void>;
  /** Title shown at the top of the dialog. */
  title: string;
  /** Main body content explaining what will happen. */
  body: ReactNode;
  /** Label for the confirm button (defaults to "Confirm"). */
  confirmLabel?: string;
  /** Label for the cancel button (defaults to "Cancel"). */
  cancelLabel?: string;
  /** Chakra color scheme for the confirm button (e.g. "red", "orange", "green"). */
  confirmColorScheme?: string;
  /** When true, confirm button shows a spinner and is disabled. */
  isConfirmLoading?: boolean;
  /** Optional text to show while confirm is loading. */
  confirmLoadingText?: string;
  /**
   * Ref passed to the least destructive action (usually Cancel),
   * so screen readers and focus behave correctly.
   */
  leastDestructiveRef?: RefObject<HTMLButtonElement>;
}

/**
 * Shared confirmation dialog for destructive or important actions.
 * Used across modules to keep confirmation UX consistent (title, copy, buttons).
 */
const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  isOpen,
  onClose,
  onConfirm,
  title,
  body,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  confirmColorScheme = "red",
  isConfirmLoading = false,
  confirmLoadingText,
  leastDestructiveRef,
}) => {
  const dialogBg = useColorModeValue("white", "gray.800");

  return (
    <AlertDialog
      isOpen={isOpen}
      leastDestructiveRef={leastDestructiveRef as any}
      onClose={onClose}
    >
      <AlertDialogOverlay>
        <AlertDialogContent bg={dialogBg}>
          <AlertDialogHeader fontSize="lg" fontWeight="bold">
            {title}
          </AlertDialogHeader>
          <AlertDialogBody>{body}</AlertDialogBody>
          <AlertDialogFooter>
            <Button
              ref={leastDestructiveRef as any}
              onClick={onClose}
              mr={3}
              variant="outline"
            >
              {cancelLabel}
            </Button>
            <Button
              colorScheme={confirmColorScheme}
              onClick={onConfirm}
              isLoading={isConfirmLoading}
              loadingText={confirmLoadingText}
            >
              {confirmLabel}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialogOverlay>
    </AlertDialog>
  );
};

export default ConfirmDialog;

