import React, { useEffect, useRef, useState } from "react";
import {
  AlertDialog,
  AlertDialogBody,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogOverlay,
  Button,
  Checkbox,
  Stack,
  Text,
  useColorModeValue,
} from "@chakra-ui/react";

const CHECKBOX_LABELS = [
  "Your personal account information, including your profile and login details, will be permanently deleted, including your activity history. This information cannot be recovered.",
  "You will lose access to all features and services associated with this account.",
  "Some account data may be retained for audit and legal compliance purposes even after deletion.",
] as const;

export interface DeleteAccountModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void | Promise<void>;
  isConfirmLoading?: boolean;
}

export default function DeleteAccountModal({
  isOpen,
  onClose,
  onConfirm,
  isConfirmLoading = false,
}: Readonly<DeleteAccountModalProps>) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const dialogBg = useColorModeValue("white", "gray.800");
  const [checked, setChecked] = useState<boolean[]>(() => CHECKBOX_LABELS.map(() => false));

  useEffect(() => {
    if (!isOpen) {
      setChecked(CHECKBOX_LABELS.map(() => false));
    }
  }, [isOpen]);

  const allChecked = checked.every(Boolean);

  const handleToggle = (index: number) => {
    setChecked((prev) => prev.map((value, i) => (i === index ? !value : value)));
  };

  return (
    <AlertDialog
      isOpen={isOpen}
      leastDestructiveRef={cancelRef}
      onClose={isConfirmLoading ? () => undefined : onClose}
      isCentered
    >
      <AlertDialogOverlay>
        <AlertDialogContent bg={dialogBg} maxW="lg">
          <AlertDialogHeader fontSize="lg" fontWeight="bold">
            Are you sure you want to delete your account?
          </AlertDialogHeader>
          <AlertDialogBody>
            <Stack spacing={4}>
              {CHECKBOX_LABELS.map((label, index) => (
                <Checkbox
                  key={label}
                  isChecked={checked[index]}
                  onChange={() => handleToggle(index)}
                  alignItems="flex-start"
                  spacing={3}
                  isDisabled={isConfirmLoading}
                >
                  <Text fontSize="sm" lineHeight="tall">
                    {label}
                  </Text>
                </Checkbox>
              ))}
            </Stack>
          </AlertDialogBody>
          <AlertDialogFooter>
            <Button
              ref={cancelRef}
              onClick={onClose}
              mr={3}
              variant="outline"
              isDisabled={isConfirmLoading}
            >
              Cancel
            </Button>
            <Button
              colorScheme="red"
              onClick={onConfirm}
              isDisabled={!allChecked}
              isLoading={isConfirmLoading}
              loadingText="Deleting..."
            >
              Delete Account
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialogOverlay>
    </AlertDialog>
  );
}
