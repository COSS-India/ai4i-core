import React, { useState } from "react";
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
import { useToastWithDeduplication } from "../../hooks/useToastWithDeduplication";
import { PASSWORD_POLICY } from "../../config/constants";
import PasswordRequirements, {
  getPasswordValidationError,
  passwordPasses,
} from "../auth/password/PasswordRequirements";

export default function ChangePasswordTab() {
  const { changePassword, isLoading } = useAuth();
  const toast = useToastWithDeduplication();
  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const validate = (): boolean => {
    const next: Record<string, string> = {};
    if (!currentPassword) {
      next.current_password = "Current password is required.";
    }
    const pwError = getPasswordValidationError(newPassword);
    if (pwError) {
      next.new_password = pwError;
    }
    if (newPassword !== confirmPassword) {
      next.confirm_password = "Passwords do not match.";
    }
    if (currentPassword && newPassword && currentPassword === newPassword) {
      next.new_password = "New password must be different from your current password.";
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    try {
      const res = await changePassword({
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setErrors({});
      toast({
        title: "Password updated",
        description: res?.message || "Your password has been changed successfully.",
        status: "success",
        duration: 5000,
        isClosable: true,
      });
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to change password. Please try again.";
      toast({
        title: "Password change failed",
        description: message,
        status: "error",
        duration: 7000,
        isClosable: true,
      });
    }
  };

  const clearFieldError = (field: string) => {
    if (errors[field]) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    }
  };

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
                    clearFieldError("current_password");
                  }}
                  autoComplete="current-password"
                  maxLength={PASSWORD_POLICY.MAX_LENGTH}
                />
                <InputRightElement width="4.5rem">
                  <IconButton
                    aria-label={showCurrent ? "Hide password" : "Show password"}
                    icon={showCurrent ? <ViewOffIcon /> : <ViewIcon />}
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
                    clearFieldError("new_password");
                  }}
                  autoComplete="new-password"
                  minLength={PASSWORD_POLICY.MIN_LENGTH}
                  maxLength={PASSWORD_POLICY.MAX_LENGTH}
                />
                <InputRightElement width="4.5rem">
                  <IconButton
                    aria-label={showNew ? "Hide password" : "Show password"}
                    icon={showNew ? <ViewOffIcon /> : <ViewIcon />}
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
              <Input
                type={showNew ? "text" : "password"}
                value={confirmPassword}
                onChange={(e) => {
                  setConfirmPassword(e.target.value);
                  clearFieldError("confirm_password");
                }}
                autoComplete="new-password"
                minLength={PASSWORD_POLICY.MIN_LENGTH}
                maxLength={PASSWORD_POLICY.MAX_LENGTH}
              />
              {errors.confirm_password && (
                <FormErrorMessage>{errors.confirm_password}</FormErrorMessage>
              )}
            </FormControl>

            <Button
              type="submit"
              colorScheme="blue"
              isLoading={isLoading}
              loadingText="Updating…"
              isDisabled={
                isLoading ||
                !currentPassword ||
                !passwordPasses(newPassword) ||
                newPassword !== confirmPassword
              }
            >
              Update Password
            </Button>
          </VStack>
        </Box>
      </CardBody>
    </Card>
  );
}
