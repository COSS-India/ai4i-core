import {
  Box,
  Drawer,
  DrawerBody,
  DrawerCloseButton,
  DrawerContent,
  DrawerFooter,
  DrawerHeader,
  DrawerOverlay,
  Flex,
} from "@chakra-ui/react";
import React from "react";
import CreateHeader from "./CreateHeader";

/**
 * `md` matches the previous default (Chakra `md`, 28rem).
 * `wide` is 40rem — the width the tier editor already used — so model review
 * and the service form fit without a dedicated page.
 */
export type FormDrawerSize = "md" | "wide";

const FORM_DRAWER_WIDE_MAX_W = "40rem";

type FormDrawerProps = {
  isOpen: boolean;
  onClose: () => void;
  title: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
  /**
   * Cancel/Close and the primary action. Pass `FormActions`.
   * Omitted on a shell that has no actions.
   */
  footer?: React.ReactNode;
  /**
   * Header controls (publish, create-from-here). The title stays on the left.
   */
  actions?: React.ReactNode;
  /** Default `md`. `wide` for long or two-column forms. */
  size?: FormDrawerSize;
  /**
   * Block overlay click, Esc, and the header close button.
   * Footer actions can still close the drawer. Use while a request is in flight.
   */
  lockDismiss?: boolean;
};

/**
 * Right-side shell for a Manage record.
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
  actions,
  size = "md",
  lockDismiss = false,
}: FormDrawerProps) {
  const wide = size === "wide";

  return (
    <Drawer
      isOpen={isOpen}
      onClose={onClose}
      placement="right"
      size={wide ? "xl" : "md"}
      closeOnOverlayClick={!lockDismiss}
      closeOnEsc={!lockDismiss}
    >
      <DrawerOverlay />
      <DrawerContent
        maxW={wide ? { base: "100%", md: FORM_DRAWER_WIDE_MAX_W } : undefined}
        sx={wide ? { maxW: { base: "100%", md: FORM_DRAWER_WIDE_MAX_W } } : undefined}
      >
        {!lockDismiss ? (
          <DrawerCloseButton
            _focus={{ boxShadow: "none" }}
            _focusVisible={{ boxShadow: "outline" }}
          />
        ) : null}
        <DrawerHeader
          px={6}
          pt={5}
          pb={4}
          borderBottomWidth="1px"
          borderColor="ink.200"
        >
          {actions ? (
            <Flex align="flex-start" justify="space-between" gap={4}>
              <Box flex="1" minW={0}>
                <CreateHeader title={title} description={description} />
              </Box>
              <Box flexShrink={0} pr={8}>
                {actions}
              </Box>
            </Flex>
          ) : (
            <CreateHeader title={title} description={description} />
          )}
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
