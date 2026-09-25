import React from "react";
import {
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalFooter,
  ModalCloseButton,
} from "@chakra-ui/react";
import CreateHeader from "./CreateHeader";
import type {
  ModalProps,
  ModalOverlayProps,
  ModalContentProps,
  ModalHeaderProps,
  ModalBodyProps,
  ModalFooterProps,
} from "@chakra-ui/react";

type StandardModalSize =
  | "xs"
  | "sm"
  | "md"
  | "lg"
  | "xl"
  | "2xl"
  | "3xl"
  | "4xl"
  | "5xl"
  | "6xl"
  | "full";

/** Semantic Create-flow sizes. Maps onto Chakra tokens without remapping existing `size`. */
export const CREATE_MODAL_SIZES = {
  md: "2xl",
  lg: "3xl",
  xl: "5xl",
} as const;

export type CreateModalSize = keyof typeof CREATE_MODAL_SIZES;

export interface StandardModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  size?: StandardModalSize;
  isCentered?: boolean;
  hideHeader?: boolean;
  hideCloseButton?: boolean;
  /**
   * Block overlay click, Esc, and the header close button.
   * Footer actions can still close the modal. Use while a request is in
   * flight or a one-time result must stay on screen.
   */
  lockDismiss?: boolean;
  closeOnOverlayClick?: ModalProps["closeOnOverlayClick"];
  closeOnEsc?: ModalProps["closeOnEsc"];
  scrollBehavior?: ModalProps["scrollBehavior"];
  modalProps?: Omit<ModalProps, "isOpen" | "onClose" | "children">;
  overlayProps?: ModalOverlayProps;
  contentProps?: ModalContentProps;
  headerProps?: ModalHeaderProps;
  bodyProps?: ModalBodyProps;
  footerProps?: ModalFooterProps;
}

export default function StandardModal({
  isOpen,
  onClose,
  title,
  description,
  children,
  footer,
  size = "md",
  isCentered = true,
  hideHeader = false,
  hideCloseButton = false,
  lockDismiss = false,
  closeOnOverlayClick = true,
  closeOnEsc = true,
  scrollBehavior,
  modalProps,
  overlayProps,
  contentProps,
  headerProps,
  bodyProps,
  footerProps,
}: StandardModalProps) {
  const scrollInside = scrollBehavior === "inside";

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size={size}
      isCentered={isCentered}
      {...modalProps}
      closeOnOverlayClick={
        lockDismiss ? false : (modalProps?.closeOnOverlayClick ?? closeOnOverlayClick)
      }
      closeOnEsc={lockDismiss ? false : (modalProps?.closeOnEsc ?? closeOnEsc)}
      scrollBehavior={scrollBehavior ?? modalProps?.scrollBehavior}
    >
      <ModalOverlay {...overlayProps} />
      <ModalContent
        borderRadius="lg"
        {...(scrollInside
          ? {
              maxH: "90vh",
              display: "flex",
              flexDirection: "column" as const,
              overflow: "hidden",
            }
          : undefined)}
        {...contentProps}
      >
        {!hideHeader && (
          <ModalHeader
            pb={description ? 2 : 3}
            {...(scrollInside
              ? { flexShrink: 0, borderBottomWidth: "1px", borderColor: "ink.200" }
              : undefined)}
            {...headerProps}
          >
            {description ? <CreateHeader title={title} description={description} /> : title}
          </ModalHeader>
        )}
        {!hideCloseButton && !lockDismiss && (
          <ModalCloseButton
            _focus={{ boxShadow: "none" }}
            _focusVisible={{ boxShadow: "outline" }}
          />
        )}
        <ModalBody
          pt={2}
          {...(scrollInside
            ? { overflowY: "auto", flex: 1, minH: 0 }
            : undefined)}
          {...bodyProps}
        >
          {children}
        </ModalBody>
        {footer !== undefined && (
          <ModalFooter
            {...(scrollInside
              ? { flexShrink: 0, borderTopWidth: "1px", borderColor: "ink.200" }
              : undefined)}
            {...footerProps}
          >
            {footer}
          </ModalFooter>
        )}
      </ModalContent>
    </Modal>
  );
}

type CreateModalProps = Omit<StandardModalProps, "size"> & {
  size?: CreateModalSize;
};

/**
 * Manage → Create overlay. Same StandardModal chrome; `size` is md / lg / xl.
 */
export function CreateModal({
  size = "md",
  scrollBehavior = "inside",
  headerProps,
  bodyProps,
  footerProps,
  modalProps,
  ...rest
}: CreateModalProps) {
  return (
    <StandardModal
      size={CREATE_MODAL_SIZES[size]}
      scrollBehavior={scrollBehavior}
      modalProps={{ blockScrollOnMount: true, ...modalProps }}
      headerProps={{ px: 6, pt: 5, pb: 4, ...headerProps }}
      bodyProps={{ px: 6, py: 5, ...bodyProps }}
      footerProps={{ px: 6, py: 4, ...footerProps }}
      {...rest}
    />
  );
}
