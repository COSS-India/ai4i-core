// DeleteDefinitionDialog

import React from "react";
import {
  AlertDialog,
  AlertDialogBody,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogOverlay,
  Button,
  Text,
} from "@chakra-ui/react";
import type { DefinitionSectionProps } from "./types";

export default function DeleteDefinitionDialog(tab: DefinitionSectionProps) {
  const { defs, defDeleteRef } = tab;

  return (
      <AlertDialog isOpen={defs.isDeleteOpen} leastDestructiveRef={defDeleteRef} onClose={defs.closeDelete}>
        <AlertDialogOverlay>
          <AlertDialogContent>
            <AlertDialogHeader fontSize="lg" fontWeight="bold">Delete Alert Definition</AlertDialogHeader>
            <AlertDialogBody><Text>Are you sure you want to delete &quot;{defs.deleteItem?.name}&quot;? This action cannot be undone.</Text></AlertDialogBody>
            <AlertDialogFooter>
              <Button ref={defDeleteRef} onClick={defs.closeDelete} isDisabled={defs.isDeleting}>Cancel</Button>
              <Button colorScheme="red" onClick={defs.handleDelete} ml={3} isLoading={defs.isDeleting} loadingText="Deleting...">Delete</Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
  );
}
