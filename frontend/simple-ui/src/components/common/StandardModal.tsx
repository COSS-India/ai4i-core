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
import type {
  ModalProps,
  ModalOverlayProps,
  ModalContentProps,
  ModalHeaderProps,
  ModalBodyProps,
  ModalFooterProps,
} from "@chakra-ui/react";

type StandardModalSize = "xs" | "sm" | "md" | "lg" | "xl" | "2xl" | "3xl" | "4xl" | "5xl" | "6xl" | "full";

export interface StandardModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  size?: StandardModalSize;
  isCentered?: boolean;
  hideHeader?: boolean;
  hideCloseButton?: boolean;
  closeOnOverlayClick?: ModalProps["closeOnOverlayClick"];
  closeOnEsc?: ModalProps["closeOnEsc"];
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
  children,
  footer,
  size = "md",
  isCentered = true,
  hideHeader = false,
  hideCloseButton = false,
  closeOnOverlayClick = true,
  closeOnEsc = true,
  modalProps,
  overlayProps,
  contentProps,
  headerProps,
  bodyProps,
  footerProps,
}: StandardModalProps) {
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size={size}
      isCentered={isCentered}
      closeOnOverlayClick={closeOnOverlayClick}
      closeOnEsc={closeOnEsc}
      {...modalProps}
    >
      <ModalOverlay {...overlayProps} />
      <ModalContent borderRadius="lg" {...contentProps}>
        {!hideHeader && (
          <ModalHeader pb={3} {...headerProps}>
            {title}
          </ModalHeader>
        )}
        {!hideCloseButton && <ModalCloseButton />}
        <ModalBody pt={2} {...bodyProps}>
          {children}
        </ModalBody>
        {footer !== undefined && <ModalFooter {...footerProps}>{footer}</ModalFooter>}
      </ModalContent>
    </Modal>
  );
}
