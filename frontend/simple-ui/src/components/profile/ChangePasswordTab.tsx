import React, { useMemo, useState } from "react";
import {
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  FormControl,
  FormErrorMessage,
  FormLabel,
  Heading,
  HStack,
  Input,
  InputGroup,
  InputRightElement,
  IconButton,
  Text,
  VStack,
  useColorModeValue,
} from "@chakra-ui/react";
import { ViewIcon, ViewOffIcon } from "@chakra-ui/icons";
import { useAuth } from "../../hooks/useAuth";
import { useToastWithDeduplication } from "../../utils/toast";
import { PASSWORD_POLICY, UI_ERROR_MESSAGES } from "../../config/constants";
import PasswordRequirements, {
  getPasswordValidationError,
  passwordPasses,
} from "../auth/password/PasswordRequirements";

const CLIENT_MESSAGES = {
  CURRENT_REQUIRED: "Current password is required.",
  NEW_SAME_AS_CURRENT: "New password must be different from your current password.",
  CONFIRM_MISMATCH: "Passwords do not match.",
} as const;

type FieldKey = "current_password" | "new_password" | "confirm_password";

interface ChangePasswordTabProps {
  onCancel?: () => void;
}

export default function ChangePasswordTab({ onCancel }: ChangePasswordTabProps) {
  const { changePassword, isLoading } = useAuth();
  const toast = useToastWithDeduplication();
  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [touched, setTouched] = useState<Partial<Record<FieldKey, boolean>>>({});
  const [serverErrors, setServerErrors] = useState<Partial<Record<FieldKey, string>>>({});

  const clientErrors = useMemo(() => {
    const next: Partial<Record<FieldKey, string>> = {};

    if (touched.current_password && !currentPassword) {
      next.current_password = CLIENT_MESSAGES.CURRENT_REQUIRED;
    }

    if (newPassword || touched.new_password) {
      if (currentPassword && newPassword && currentPassword === newPassword) {
        next.new_password = CLIENT_MESSAGES.NEW_SAME_AS_CURRENT;
      } else {
        const pwError = getPasswordValidationError(newPassword);
        if (pwError) {
          next.new_password = pwError;
        }
      }
    }

    if (confirmPassword || touched.confirm_password) {
      if (confirmPassword && newPassword !== confirmPassword) {
        next.confirm_password = CLIENT_MESSAGES.CONFIRM_MISMATCH;
      }
    }

    return next;
  }, [currentPassword, newPassword, confirmPassword, touched]);

  const errors = { ...clientErrors, ...serverErrors };

  const markTouched = (field: FieldKey) => {
    setTouched((prev) => ({ ...prev, [field]: true }));
  };

  const clearServerError = (field: FieldKey) => {
    if (serverErrors[field]) {
      setServerErrors((prev) => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    }
  };

  const resetForm = () => {
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setShowCurrent(false);
    setShowNew(false);
    setShowConfirm(false);
    setTouched({});
    setServerErrors({});
  };

  const handleCancel = () => {
    resetForm();
    onCancel?.();
  };

  const getSubmitErrors = (): Partial<Record<FieldKey, string>> => {
    const next: Partial<Record<FieldKey, string>> = {};

    if (!currentPassword) {
      next.current_password = CLIENT_MESSAGES.CURRENT_REQUIRED;
    }
    if (currentPassword && newPassword && currentPassword === newPassword) {
      next.new_password = CLIENT_MESSAGES.NEW_SAME_AS_CURRENT;
    } else {
      const pwError = getPasswordValidationError(newPassword);
      if (pwError) {
        next.new_password = pwError;
      }
    }
    if (newPassword !== confirmPassword) {
      next.confirm_password = CLIENT_MESSAGES.CONFIRM_MISMATCH;
    }

    return next;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setTouched({
      current_password: true,
      new_password: true,
      confirm_password: true,
    });

    if (Object.keys(getSubmitErrors()).length > 0) {
      return;
    }

    try {
      const res = await changePassword({
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword,
      });
      resetForm();
      toast({
        title: "Password updated",
        description: res?.message || "Your password has been changed successfully.",
        status: "success",
        duration: 5000,
        isClosable: true,
      });
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : UI_ERROR_MESSAGES.PASSWORD_CHANGE_FAILED;
      const lower = message.toLowerCase();
      if (lower.includes("current password")) {
        setServerErrors((prev) => ({ ...prev, current_password: message }));
      }
      toast({
        title: "Password change failed",
        description: message,
        status: "error",
        duration: 7000,
        isClosable: true,
      });
    }
  };

  const canSubmit =
    !isLoading &&
    !!currentPassword &&
    passwordPasses(newPassword) &&
    newPassword !== currentPassword &&
    newPassword === confirmPassword;

  return (
    <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
      <CardHeader pb={3}>
        <Heading size="md" color="gray.700">
          Change Password
        </Heading>
        <Text fontSize="sm" color="gray.500" mt={1}>
          Update your account password. Must meet all security requirements below.
        </Text>
      </CardHeader>
      <CardBody pt={2}>
        <Box as="form" onSubmit={handleSubmit}>
          <VStack spacing={4} align="stretch">
            <FormControl isRequired isInvalid={!!errors.current_password}>
              <FormLabel>Current Password</FormLabel>
              <InputGroup>
                <Input
                  type={showCurrent ? "text" : "password"}
                  value={currentPassword}
                  onChange={(e) => {
                    setCurrentPassword(e.target.value);
                    markTouched("current_password");
                    clearServerError("current_password");
                  }}
                  onBlur={() => markTouched("current_password")}
                  autoComplete="current-password"
                  maxLength={PASSWORD_POLICY.MAX_LENGTH}
                />
                <InputRightElement width="4.5rem">
                  <IconButton
                    aria-label={showCurrent ? "Hide password" : "Show password"}
                    icon={showCurrent ? <ViewIcon /> : <ViewOffIcon />}
                    h="1.75rem"
                    size="sm"
                    onClick={() => setShowCurrent((v) => !v)}
                    variant="ghost"
                  />
                </InputRightElement>
              </InputGroup>
              {errors.current_password && (
                <FormErrorMessage>{errors.current_password}</FormErrorMessage>
              )}
            </FormControl>

            <FormControl isRequired isInvalid={!!errors.new_password}>
              <FormLabel>New Password</FormLabel>
              <InputGroup>
                <Input
                  type={showNew ? "text" : "password"}
                  value={newPassword}
                  onChange={(e) => {
                    setNewPassword(e.target.value);
                    markTouched("new_password");
                    clearServerError("new_password");
                  }}
                  onBlur={() => markTouched("new_password")}
                  autoComplete="new-password"
                  minLength={PASSWORD_POLICY.MIN_LENGTH}
                  maxLength={PASSWORD_POLICY.MAX_LENGTH}
                />
                <InputRightElement width="4.5rem">
                  <IconButton
                    aria-label={showNew ? "Hide password" : "Show password"}
                    icon={showNew ? <ViewIcon /> : <ViewOffIcon />}
                    h="1.75rem"
                    size="sm"
                    onClick={() => setShowNew((v) => !v)}
                    variant="ghost"
                  />
                </InputRightElement>
              </InputGroup>
              {errors.new_password && (
                <FormErrorMessage>{errors.new_password}</FormErrorMessage>
              )}
              <PasswordRequirements password={newPassword} compact />
            </FormControl>

            <FormControl isRequired isInvalid={!!errors.confirm_password}>
              <FormLabel>Confirm New Password</FormLabel>
              <InputGroup>
                <Input
                  type={showConfirm ? "text" : "password"}
                  value={confirmPassword}
                  onChange={(e) => {
                    setConfirmPassword(e.target.value);
                    markTouched("confirm_password");
                    clearServerError("confirm_password");
                  }}
                  onBlur={() => markTouched("confirm_password")}
                  autoComplete="new-password"
                  minLength={PASSWORD_POLICY.MIN_LENGTH}
                  maxLength={PASSWORD_POLICY.MAX_LENGTH}
                />
                <InputRightElement width="4.5rem">
                  <IconButton
                    aria-label={showConfirm ? "Hide password" : "Show password"}
                    icon={showConfirm ? <ViewIcon /> : <ViewOffIcon />}
                    h="1.75rem"
                    size="sm"
                    onClick={() => setShowConfirm((v) => !v)}
                    variant="ghost"
                  />
                </InputRightElement>
              </InputGroup>
              {errors.confirm_password && (
                <FormErrorMessage>{errors.confirm_password}</FormErrorMessage>
              )}
            </FormControl>

            <HStack spacing={3}>
              <Button
                type="submit"
                colorScheme="blue"
                isLoading={isLoading}
                loadingText="Updating…"
                isDisabled={!canSubmit}
              >
                Update Password
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={handleCancel}
                isDisabled={isLoading}
              >
                Cancel
              </Button>
            </HStack>
          </VStack>
        </Box>
      </CardBody>
    </Card>
  );
}
