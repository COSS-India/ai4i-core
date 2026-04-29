// Email-verification page consumed by the link in the verify-email email.
// Reads ?token= from the URL, POSTs it to /api/v1/auth/verify-email, then
// shows success / failure with a path forward.

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
  Spinner,
  Stack,
  Text,
  VStack,
  useColorModeValue,
} from "@chakra-ui/react";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import React, { useEffect, useRef, useState } from "react";
import { authService } from "../../services/authService";

type Phase =
  | { kind: "loading" }
  | { kind: "success"; message: string }
  | { kind: "error"; message: string };

type ResendPhase =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "sent"; message: string }
  | { kind: "failed"; message: string };

const VerifyEmailPage: React.FC = () => {
  const router = useRouter();
  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");
  const pageBg = useColorModeValue("gray.50", "gray.900");

  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
  const [resendPhase, setResendPhase] = useState<ResendPhase>({ kind: "idle" });
  const [resendEmail, setResendEmail] = useState("");
  // StrictMode in dev mounts twice; guard so the one-time token isn't
  // consumed on the first mount and reported as "already used" on the second.
  const fired = useRef(false);

  useEffect(() => {
    if (!router.isReady || fired.current) return;
    const raw = router.query.token;
    const token =
      typeof raw === "string" ? raw : Array.isArray(raw) ? raw[0] : "";
    if (!token) {
      setPhase({ kind: "error", message: "Verification link is missing a token." });
      return;
    }
    fired.current = true;
    authService
      .verifyEmail({ token })
      .then((res) =>
        setPhase({
          kind: "success",
          message: res?.message || "Email verified. You can now sign in.",
        })
      )
      .catch((err) =>
        setPhase({
          kind: "error",
          message:
            err?.message ||
            "Verification failed. The link may be expired or already used.",
        })
      );
  }, [router.isReady, router.query.token]);

  return (
    <>
      <Head>
        <title>Verify your email — AI4I Platform</title>
      </Head>
      <Box minH="100vh" bg={pageBg} py={{ base: 8, md: 16 }}>
        <Container maxW="md">
          <VStack spacing={6} align="stretch">
            <Heading size="lg" textAlign="center">
              Verify your email
            </Heading>

            <Card bg={cardBg} borderWidth="1px" borderColor={cardBorder}>
              <CardBody>
                {phase.kind === "loading" && (
                  <VStack py={6}>
                    <Spinner />
                    <Text color="gray.500">Verifying your email…</Text>
                  </VStack>
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

                {phase.kind === "error" && (
                  <VStack align="stretch" spacing={4}>
                    <Alert status="error" rounded="md">
                      <AlertIcon />
                      {phase.message}
                    </Alert>

                    {/* Resend-verification form, shown on any error so users
                        can recover from expired/used/invalid links. */}
                    <Box borderTopWidth="1px" pt={4}>
                      <Text fontSize="sm" color="gray.600" mb={3}>
                        Request a new verification link:
                      </Text>
                      <form
                        onSubmit={async (e) => {
                          e.preventDefault();
                          if (!resendEmail) return;
                          setResendPhase({ kind: "submitting" });
                          try {
                            const res = await authService.resendVerification({
                              email: resendEmail,
                            });
                            setResendPhase({
                              kind: "sent",
                              message:
                                res?.message ||
                                "If that account exists and isn't verified yet, a new link has been sent.",
                            });
                          } catch (err: any) {
                            setResendPhase({
                              kind: "failed",
                              message:
                                err?.message ||
                                "Could not resend verification email.",
                            });
                          }
                        }}
                      >
                        <Stack spacing={3}>
                          <FormControl isRequired>
                            <FormLabel fontSize="sm">Email</FormLabel>
                            <Input
                              type="email"
                              value={resendEmail}
                              onChange={(e) => setResendEmail(e.target.value)}
                              placeholder="you@example.com"
                              size="sm"
                            />
                          </FormControl>
                          {resendPhase.kind === "sent" && (
                            <Alert status="success" rounded="md" size="sm">
                              <AlertIcon />
                              {resendPhase.message}
                            </Alert>
                          )}
                          {resendPhase.kind === "failed" && (
                            <Alert status="error" rounded="md" size="sm">
                              <AlertIcon />
                              {resendPhase.message}
                            </Alert>
                          )}
                          <Button
                            type="submit"
                            colorScheme="blue"
                            size="sm"
                            isLoading={resendPhase.kind === "submitting"}
                            loadingText="Sending…"
                            isDisabled={resendPhase.kind === "sent"}
                          >
                            Resend verification email
                          </Button>
                        </Stack>
                      </form>
                    </Box>

                    <Link href="/auth" passHref legacyBehavior>
                      <Button as="a" colorScheme="blue" variant="outline">
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

export default VerifyEmailPage;
