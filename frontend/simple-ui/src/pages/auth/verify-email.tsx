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
  Heading,
  Spinner,
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

const VerifyEmailPage: React.FC = () => {
  const router = useRouter();
  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");
  const pageBg = useColorModeValue("gray.50", "gray.900");

  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
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
                    <Text fontSize="sm" color="gray.500">
                      If the link is expired or already used, contact your
                      administrator or sign up again.
                    </Text>
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
