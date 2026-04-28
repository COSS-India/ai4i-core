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
import { authService } from "../../services/authService";
import { SetPasswordStatusResponse } from "../../types/auth";

type Phase =
  | { kind: "loading" }
  | { kind: "invalid"; status: SetPasswordStatusResponse["status"]; message: string }
  | { kind: "ready" }
  | { kind: "submitting" }
  | { kind: "success"; message: string }
  | { kind: "error"; message: string };

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
        status: "invalid",
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
          status: "invalid",
          message: err?.message || "Could not validate the setup link.",
        });
      });
  }, [router.isReady, router.query.token]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword.length < 8) {
      setPhase({ kind: "error", message: "Password must be at least 8 characters." });
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
        <title>Set your password — AI4I Platform</title>
      </Head>
      <Box minH="100vh" bg={pageBg} py={{ base: 8, md: 16 }}>
        <Container maxW="md">
          <VStack spacing={6} align="stretch">
            <Heading size="lg" textAlign="center">
              Set your password
            </Heading>

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
                    <Alert status={phase.status === "expired" ? "warning" : "error"} rounded="md">
                      <AlertIcon />
                      {phase.message}
                    </Alert>
                    <Text fontSize="sm" color="gray.500">
                      {phase.status === "expired" || phase.status === "used"
                        ? "Ask your administrator to send you a new setup link, or request one from the login page."
                        : "Make sure you used the most recent setup link."}
                    </Text>
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
                      <Text fontSize="sm" color="gray.500">
                        Choose a password to activate your account.
                      </Text>
                      <FormControl isRequired>
                        <FormLabel>New password</FormLabel>
                        <InputGroup>
                          <Input
                            type={showPw ? "text" : "password"}
                            value={newPassword}
                            onChange={(e) => setNewPassword(e.target.value)}
                            autoComplete="new-password"
                            minLength={8}
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
                      </FormControl>
                      <FormControl isRequired>
                        <FormLabel>Confirm password</FormLabel>
                        <Input
                          type={showPw ? "text" : "password"}
                          value={confirmPassword}
                          onChange={(e) => setConfirmPassword(e.target.value)}
                          autoComplete="new-password"
                          minLength={8}
                        />
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
                      >
                        Set password
                      </Button>
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
