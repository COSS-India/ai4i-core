import {
  Drawer,
  DrawerBody,
  DrawerCloseButton,
  DrawerContent,
  DrawerFooter,
  DrawerHeader,
  DrawerOverlay,
} from "@chakra-ui/react";
import React from "react";
import CreateHeader from "./CreateHeader";

type FormDrawerProps = {
  isOpen: boolean;
  onClose: () => void;
  title: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
  /**
   * Cancel/Back and the primary action. Pass `FormActions`.
   * Omitted on a shell that has no actions.
   */
  footer?: React.ReactNode;
};

/**
 * Right-side shell for a short Manage record.
 * The page underneath stays mounted. No breadcrumbs and no routing.
 * Field sections stay in the caller.
 */
export default function FormDrawer({
  isOpen,
  onClose,
  title,
  description,
  children,
  footer,
}: FormDrawerProps) {
  return (
    <Drawer isOpen={isOpen} onClose={onClose} placement="right" size="md">
      <DrawerOverlay />
      <DrawerContent>
        <DrawerCloseButton
          _focus={{ boxShadow: "none" }}
          _focusVisible={{ boxShadow: "outline" }}
        />
        <DrawerHeader
          px={6}
          pt={5}
          pb={4}
          borderBottomWidth="1px"
          borderColor="ink.200"
        >
          <CreateHeader title={title} description={description} />
        </DrawerHeader>
        <DrawerBody px={6} py={5}>
          {children}
        </DrawerBody>
        {footer ? (
          <DrawerFooter
            px={6}
            py={4}
            borderTopWidth="1px"
            borderColor="ink.200"
          >
            {footer}
          </DrawerFooter>
        ) : null}
      </DrawerContent>
    </Drawer>
  );
}
