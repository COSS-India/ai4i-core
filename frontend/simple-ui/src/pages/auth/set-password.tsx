// Set-password page consumed by the activation link in setup_link emails.
// Reads ?token= from the URL, validates it via the backend, then collects a
// new password and POSTs it to /api/v1/auth/set-password.

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
  Spinner,
  Stack,
  Text,
  VStack,
  useColorModeValue,
} from "@chakra-ui/react";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import React, { useEffect, useState } from "react";
import { SET_PASSWORD_TOKEN, isSetPasswordTokenStatus } from "../../config/constants";
import { getPlatformName } from "../../config/runtimeConfig";
import { authService } from "../../services/authService";
import { SetPasswordStatusResponse } from "../../types/auth";
import { PASSWORD_POLICY } from "../../config/constants";
import PasswordRequirements, { getPasswordValidationError, passwordPasses } from "../../components/auth/password/PasswordRequirements";

type Phase =
  | { kind: "loading" }
  | { kind: "invalid"; status: SetPasswordStatusResponse["status"]; message: string }
  | { kind: "ready" }
  | { kind: "submitting" }
  | { kind: "success"; message: string }
  | { kind: "error"; message: string };

// Inline component shown on the invalid/expired/used state so users can
// recover without leaving the page. Calls /auth/resend-setup-link.
const ResendSetupLinkForm: React.FC = () => {
  const [email, setEmail] = useState("");
  const [phase, setPhase] = useState<
    | { kind: "idle" }
    | { kind: "submitting" }
    | { kind: "sent"; message: string }
    | { kind: "failed"; message: string }
  >({ kind: "idle" });

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) return;
    setPhase({ kind: "submitting" });
    try {
      const res = await authService.resendSetupLink({ email });
      const msg =
        res?.message ||
        "If the account exists and isn't activated yet, a new setup link has been sent.";
      setPhase({ kind: "sent", message: msg });
    } catch (err: any) {
      const data = err?.response?.data;
      const msg = data?.detail?.message || data?.detail || err?.message || "Could not resend.";
      setPhase({ kind: "failed", message: msg });
    }
  };

  return (
    <form onSubmit={onSubmit}>
      <Stack spacing={3}>
        <FormControl isRequired>
          <FormLabel fontSize="sm">Email</FormLabel>
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            size="sm"
          />
        </FormControl>
        {phase.kind === "sent" && (
          <Alert status="success" rounded="md" size="sm">
            <AlertIcon />
            {phase.message}
          </Alert>
        )}
        {phase.kind === "failed" && (
          <Alert status="error" rounded="md" size="sm">
            <AlertIcon />
            {phase.message}
          </Alert>
        )}
        <Button
          type="submit"
          colorScheme="blue"
          size="sm"
          isLoading={phase.kind === "submitting"}
          loadingText="Sending…"
          isDisabled={phase.kind === "sent"}
        >
          Resend setup link
        </Button>
      </Stack>
    </form>
  );
};

const SetPasswordPage: React.FC = () => {
  const router = useRouter();
  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");
  const pageBg = useColorModeValue("gray.50", "gray.900");

  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
  const [token, setToken] = useState<string>("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPw, setShowPw] = useState(false);

  useEffect(() => {
    if (!router.isReady) return;
    const raw = router.query.token;
    const t = typeof raw === "string" ? raw : Array.isArray(raw) ? raw[0] : "";
    if (!t) {
      setPhase({
        kind: "invalid",
        status: SET_PASSWORD_TOKEN.STATUS.INVALID,
        message: "Setup link is missing a token.",
      });
      return;
    }
    setToken(t);
    authService
      .getSetPasswordStatus(t)
      .then((status) => {
        if (status.valid) {
          setPhase({ kind: "ready" });
        } else {
          setPhase({ kind: "invalid", status: status.status, message: status.message });
        }
      })
      .catch((err) => {
        setPhase({
          kind: "invalid",
          status: SET_PASSWORD_TOKEN.STATUS.INVALID,
          message: err?.message || "Could not validate the setup link.",
        });
      });
  }, [router.isReady, router.query.token]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const passwordError = getPasswordValidationError(newPassword);
    if (passwordError) {
      setPhase({ kind: "error", message: passwordError });
      return;
    }
    if (newPassword !== confirmPassword) {
      setPhase({ kind: "error", message: "Passwords do not match." });
      return;
    }
    setPhase({ kind: "submitting" });
    try {
      const res = await authService.setPasswordWithToken({
        token,
        new_password: newPassword,
        confirm_password: confirmPassword,
      });
      setPhase({
        kind: "success",
        message: res?.message || "Password set. You can now sign in.",
      });
    } catch (err: any) {
      setPhase({
        kind: "error",
        message: err?.message || "Failed to set password. Try requesting a new link.",
      });
    }
  };

  return (
    <>
      <Head>
        <title>{`Set Your Password — ${getPlatformName()}`}</title>
      </Head>
      <Box minH="100vh" bg={pageBg} py={{ base: 8, md: 16 }}>
        <Container maxW="md">
          <VStack spacing={3} align="stretch">
            <Heading size="lg" textAlign="center">
              Set Your Password
            </Heading>
            <Text textAlign="center" fontSize="sm" color="gray.600">
              Please create a strong password to secure your account.
            </Text>

            <Card bg={cardBg} borderWidth="1px" borderColor={cardBorder}>
              <CardBody>
                {phase.kind === "loading" && (
                  <VStack py={6}>
                    <Spinner />
                    <Text color="gray.500">Validating setup link…</Text>
                  </VStack>
                )}

                {phase.kind === "invalid" && (
                  <VStack align="stretch" spacing={4}>
                    <Alert
                      status={
                        isSetPasswordTokenStatus(phase.status, SET_PASSWORD_TOKEN.STATUS.EXPIRED)
                          ? "warning"
                          : "error"
                      }
                      rounded="md"
                    >
                      <AlertIcon />
                      {phase.message}
                    </Alert>

                    {/* Resend setup-link form — recovery path per security spec */}
                    <Box borderTopWidth="1px" pt={4}>
                      <Text fontSize="sm" color="gray.600" mb={3}>
                        Request a new setup link by entering the email your account was created with:
                      </Text>
                      <ResendSetupLinkForm />
                    </Box>

                    <Link href="/auth" passHref legacyBehavior>
                      <Button as="a" colorScheme="blue" variant="outline">
                        Go to sign in
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
                        <FormLabel>New Password</FormLabel>
                        <InputGroup>
                          <Input
                            type={showPw ? "text" : "password"}
                            value={newPassword}
                            onChange={(e) => setNewPassword(e.target.value)}
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
                        <FormLabel>Confirm Password</FormLabel>
                        <Input
                          type={showPw ? "text" : "password"}
                          value={confirmPassword}
                          onChange={(e) => setConfirmPassword(e.target.value)}
                          autoComplete="new-password"
                          minLength={PASSWORD_POLICY.MIN_LENGTH}
                          maxLength={PASSWORD_POLICY.MAX_LENGTH}
                        />
                        {confirmPassword.length > 0 && confirmPassword !== newPassword && (
                          <Text color="red.500" fontSize="sm" mt={1}>
                            Passwords do not match.
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
                        loadingText="Setting password…"
                        isDisabled={!passwordPasses(newPassword) || newPassword !== confirmPassword}
                      >
                        Set Password
                      </Button>
                      <Text textAlign="center" fontSize="sm" color="gray.500">
                        Having trouble? Contact your administrator.
                      </Text>
                    </Stack>
                  </form>
                )}

                {phase.kind === "success" && (
                  <VStack align="stretch" spacing={4}>
                    <Alert status="success" rounded="md">
                      <AlertIcon />
                      {phase.message}
                    </Alert>
                    <Link href="/auth" passHref legacyBehavior>
                      <Button as="a" colorScheme="blue">
                        Go to sign in
                      </Button>
                    </Link>
                  </VStack>
                )}
              </CardBody>
            </Card>
          </VStack>
        </Container>
      </Box>
    </>
  );
};

export default SetPasswordPage;
