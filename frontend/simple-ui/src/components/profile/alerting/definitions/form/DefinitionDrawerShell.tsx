import {
  Button,
  Drawer,
  DrawerBody,
  DrawerCloseButton,
  DrawerContent,
  DrawerFooter,
  DrawerHeader,
  DrawerOverlay,
  Text,
} from "@chakra-ui/react";
import type { ReactNode } from "react";

interface DefinitionDrawerShellProps {
  title: string;
  isOpen: boolean;
  onClose: () => void;
  isSaving: boolean;
  saveLabel: string;
  onSave: () => void;
  saveDisabled?: boolean;
  children: ReactNode;
}

export default function DefinitionDrawerShell({
  title,
  isOpen,
  onClose,
  isSaving,
  saveLabel,
  onSave,
  saveDisabled = false,
  children,
}: DefinitionDrawerShellProps) {
  return (
    <Drawer isOpen={isOpen} onClose={onClose} placement="right" size="md">
      <DrawerOverlay />
      <DrawerContent>
        <DrawerCloseButton />
        <DrawerHeader borderBottomWidth="1px" borderColor="gray.200">
          <Text fontSize="lg" fontWeight="bold">
            {title}
          </Text>
        </DrawerHeader>
        <DrawerBody py={6}>{children}</DrawerBody>
        <DrawerFooter borderTopWidth="1px" borderColor="gray.200">
          <Button variant="outline" mr={3} onClick={onClose} isDisabled={isSaving}>
            Cancel
          </Button>
          <Button
            colorScheme="orange"
            onClick={onSave}
            isLoading={isSaving}
            loadingText="Saving..."
            isDisabled={saveDisabled || isSaving}
          >
            {saveLabel}
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}
