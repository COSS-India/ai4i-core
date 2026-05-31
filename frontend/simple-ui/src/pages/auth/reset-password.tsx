// Reset-password page — consumed by the reset link in the password-reset email.
// Reads ?token= from URL, collects new password + confirm, POSTs to /auth/reset-password.
// On success, server has already revoked all refresh tokens (other sessions
// signed out). User is then redirected to /auth.

import {
  Alert,
  AlertIcon,
  Box,
  Button,
  Card,
  CardBody,
  Container,
  FormControl,
  FormLabel,
  Heading,
  Input,
  InputGroup,
  InputRightElement,
  Stack,
  Text,
  VStack,
  useColorModeValue,
} from "@chakra-ui/react";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import React, { useEffect, useState } from "react";
import { authService } from "../../services/authService";
import { PASSWORD_POLICY } from "../../config/constants";
import PasswordRequirements, { getPasswordValidationError, passwordPasses } from "../../components/auth/password/PasswordRequirements";

type Phase =
  | { kind: "ready" }
  | { kind: "no-token" }
  | { kind: "submitting" }
  | { kind: "success"; message: string }
  | { kind: "error"; message: string };

const ResetPasswordPage: React.FC = () => {
  const router = useRouter();
  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");
  const pageBg = useColorModeValue("gray.50", "gray.900");

  const [token, setToken] = useState("");
  const [phase, setPhase] = useState<Phase>({ kind: "ready" });
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [pwErr, setPwErr] = useState<string | null>(null);

  useEffect(() => {
    if (!router.isReady) return;
    const raw = router.query.token;
    const t = typeof raw === "string" ? raw : Array.isArray(raw) ? raw[0] : "";
    if (!t) {
      setPhase({ kind: "no-token" });
      return;
    }
    setToken(t);
    setPhase({ kind: "ready" });
  }, [router.isReady, router.query.token]);

  const validate = (): string | null => {
    const passwordError = getPasswordValidationError(newPassword);
    if (passwordError) return passwordError;
    if (newPassword !== confirmPassword) return "Passwords do not match.";
    return null;
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const err = validate();
    setPwErr(err);
    if (err) return;
    setPhase({ kind: "submitting" });
    try {
      const res = await authService.resetPassword({
        token,
        new_password: newPassword,
        confirm_password: confirmPassword,
      });
      setPhase({
        kind: "success",
        message: res?.message || "Password reset successfully.",
      });
    } catch (e: any) {
      setPhase({
        kind: "error",
        message: e?.message ||
          "Reset failed. The link may be expired or already used. Request a new link from the Forgot Password page.",
      });
    }
  };

  return (
    <>
      <Head>
        <title>Reset Password — AI4I Platform</title>
      </Head>
      <Box minH="100vh" bg={pageBg} py={{ base: 8, md: 16 }}>
        <Container maxW="md">
          <VStack spacing={6} align="stretch">
            <Heading size="lg" textAlign="center">
              Reset Password
            </Heading>

            <Card bg={cardBg} borderWidth="1px" borderColor={cardBorder}>
              <CardBody>
                {phase.kind === "no-token" && (
                  <VStack align="stretch" spacing={4}>
                    <Alert status="error" rounded="md">
                      <AlertIcon />
                      Reset link is missing a token.
                    </Alert>
                    <Link href="/auth/forgot-password" passHref legacyBehavior>
                      <Button as="a" colorScheme="blue">
                        Request a new link
                      </Button>
                    </Link>
                  </VStack>
                )}

                {phase.kind === "success" && (
                  <VStack align="stretch" spacing={4}>
                    <Alert status="success" rounded="md">
                      <AlertIcon />
                      {phase.message}
                    </Alert>
                    <Text fontSize="sm" color="gray.500">
                      For your security, you&rsquo;ve been signed out of all
                      other sessions. Sign in with your new password.
                    </Text>
                    <Link href="/auth" passHref legacyBehavior>
                      <Button as="a" colorScheme="blue">
                        Return to Sign In
                      </Button>
                    </Link>
                  </VStack>
                )}

                {(phase.kind === "ready" ||
                  phase.kind === "submitting" ||
                  phase.kind === "error") && (
                  <form onSubmit={onSubmit}>
                    <Stack spacing={4}>
                      <FormControl isRequired>
                        <FormLabel>New Password *</FormLabel>
                        <InputGroup>
                          <Input
                            type={showPw ? "text" : "password"}
                            value={newPassword}
                            onChange={(e) => {
                              setNewPassword(e.target.value);
                              if (pwErr) setPwErr(null);
                            }}
                            autoComplete="new-password"
                            minLength={PASSWORD_POLICY.MIN_LENGTH}
                            maxLength={PASSWORD_POLICY.MAX_LENGTH}
                          />
                          <InputRightElement width="auto" pr={2}>
                            <Button
                              size="xs"
                              variant="ghost"
                              onClick={() => setShowPw((v) => !v)}
                              tabIndex={-1}
                            >
                              {showPw ? "Hide" : "Show"}
                            </Button>
                          </InputRightElement>
                        </InputGroup>
                        <PasswordRequirements password={newPassword} compact />
                      </FormControl>

                      <FormControl isRequired isInvalid={confirmPassword.length > 0 && confirmPassword !== newPassword}>
                        <FormLabel>Confirm Password *</FormLabel>
                        <Input
                          type={showPw ? "text" : "password"}
                          value={confirmPassword}
                          onChange={(e) => {
                            setConfirmPassword(e.target.value);
                            if (pwErr) setPwErr(null);
                          }}
                          autoComplete="new-password"
                          minLength={PASSWORD_POLICY.MIN_LENGTH}
                          maxLength={PASSWORD_POLICY.MAX_LENGTH}
                        />
                        {confirmPassword.length > 0 && confirmPassword !== newPassword && (
                          <Text color="red.500" fontSize="sm" mt={1}>
                            Passwords do not match.
                          </Text>
                        )}
                        {pwErr && pwErr !== "Passwords do not match." && (
                          <Text color="red.500" fontSize="sm" mt={1}>
                            {pwErr}
                          </Text>
                        )}
                      </FormControl>

                      {phase.kind === "error" && (
                        <Alert status="error" rounded="md">
                          <AlertIcon />
                          {phase.message}
                        </Alert>
                      )}

                      <Button
                        type="submit"
                        colorScheme="blue"
                        isLoading={phase.kind === "submitting"}
                        loadingText="Resetting…"
                        isDisabled={!passwordPasses(newPassword) || newPassword !== confirmPassword}
                      >
                        Reset Password
                      </Button>

                      <Box textAlign="center">
                        <Link href="/auth" passHref legacyBehavior>
                          <Text as="a" color="blue.500" fontSize="sm">
                            Return to Sign In
                          </Text>
                        </Link>
                      </Box>
                    </Stack>
                  </form>
                )}
              </CardBody>
            </Card>
          </VStack>
        </Container>
      </Box>
    </>
  );
};

export default ResetPasswordPage;
