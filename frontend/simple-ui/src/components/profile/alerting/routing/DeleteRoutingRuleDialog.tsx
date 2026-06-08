// DeleteRoutingRuleDialog

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
import type { RoutingSectionProps } from "./types";

export default function DeleteRoutingRuleDialog(tab: RoutingSectionProps) {
  const { rules, ruleDeleteRef } = tab;

  return (
      <AlertDialog isOpen={rules.isDeleteOpen} leastDestructiveRef={ruleDeleteRef} onClose={rules.closeDelete}>
        <AlertDialogOverlay>
          <AlertDialogContent>
            <AlertDialogHeader fontSize="lg" fontWeight="bold">Delete Routing Rule</AlertDialogHeader>
            <AlertDialogBody><Text>Are you sure you want to delete &quot;{rules.deleteItem?.rule_name}&quot;? This action cannot be undone.</Text></AlertDialogBody>
            <AlertDialogFooter>
              <Button ref={ruleDeleteRef} onClick={rules.closeDelete} isDisabled={rules.isDeleting}>Cancel</Button>
              <Button colorScheme="red" onClick={rules.handleDelete} ml={3} isLoading={rules.isDeleting} loadingText="Deleting...">Delete</Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
  );
}
