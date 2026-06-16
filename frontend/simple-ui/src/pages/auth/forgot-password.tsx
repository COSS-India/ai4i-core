// Forgot-password page — collects an email and POSTs to /auth/forgot-password.
// Backend always returns 200 with a generic message regardless of whether the
// email is registered (anti-enumeration). Rate-limited to 3/hour/email server-side;
// 429s surface as a clear "try later" error.

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
  Stack,
  Text,
  VStack,
  useColorModeValue,
} from "@chakra-ui/react";
import Head from "next/head";
import Link from "next/link";
import React, { useState } from "react";
import { authService } from "../../services/authService";

type Phase =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "sent"; message: string }
  | { kind: "rate_limited"; message: string }
  | { kind: "error"; message: string };

const ForgotPasswordPage: React.FC = () => {
  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");
  const pageBg = useColorModeValue("gray.50", "gray.900");

  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });

  const validate = (value: string): string | null => {
    if (!value) return "Please enter your email address.";
    if (!/^[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+$/.test(value)) return "Please enter a valid email address.";
    return null;
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const err = validate(email);
    setEmailError(err);
    if (err) return;
    setPhase({ kind: "submitting" });
    try {
      const res = await authService.requestPasswordReset({ email });
      setPhase({
        kind: "sent",
        message: res?.message ||
          "If this email is registered, you'll receive a reset link shortly.",
      });
    } catch (e: any) {
      // Rate-limit (HTTP 429) shows a distinct message; other errors show generic.
      const msg = e?.message || "Could not request reset. Try again later.";
      const isRateLimit = /Too many|RESET_RATE_LIMITED|429/i.test(msg);
      setPhase(
        isRateLimit
          ? { kind: "rate_limited", message: "Too many reset requests for this email. Please wait an hour before trying again." }
          : { kind: "error", message: msg }
      );
    }
  };

  return (
    <>
      <Head>
        <title>Forgot Password — AI4I Platform</title>
      </Head>
      <Box minH="100vh" bg={pageBg} py={{ base: 8, md: 16 }}>
        <Container maxW="md">
          <VStack spacing={6} align="stretch">
            <Heading size="lg" textAlign="center">
              Forgot Password
            </Heading>
            <Text textAlign="center" fontSize="sm" color="gray.500">
              Enter your registered email address and we&rsquo;ll send you a reset link.
            </Text>

            <Card bg={cardBg} borderWidth="1px" borderColor={cardBorder}>
              <CardBody>
                <form onSubmit={onSubmit} noValidate>
                  <Stack spacing={4}>
                    <FormControl isRequired isInvalid={!!emailError}>
                      <FormLabel>Email *</FormLabel>
                      <Input
                        type="email"
                        value={email}
                        onChange={(e) => {
                          setEmail(e.target.value);
                          if (emailError) setEmailError(validate(e.target.value));
                        }}
                        placeholder="you@example.com"
                        autoComplete="email"
                        isDisabled={phase.kind === "sent"}
                      />
                      {emailError && (
                        <Text color="red.500" fontSize="sm" mt={1}>
                          {emailError}
                        </Text>
                      )}
                    </FormControl>

                    <Button
                      type="submit"
                      colorScheme="blue"
                      isLoading={phase.kind === "submitting"}
                      loadingText="Sending…"
                      isDisabled={phase.kind === "sent"}
                    >
                      Send Reset Link
                    </Button>

                    {/* Status banners stay below the form (matches reference UI) */}
                    {phase.kind === "sent" && (
                      <Alert status="success" rounded="md">
                        <AlertIcon />
                        {phase.message}
                      </Alert>
                    )}
                    {phase.kind === "rate_limited" && (
                      <Alert status="warning" rounded="md">
                        <AlertIcon />
                        {phase.message}
                      </Alert>
                    )}
                    {phase.kind === "error" && (
                      <Alert status="error" rounded="md">
                        <AlertIcon />
                        {phase.message}
                      </Alert>
                    )}

                    <Box textAlign="center">
                      <Link href="/auth" passHref legacyBehavior>
                        <Text as="a" color="blue.500" fontSize="sm">
                          ← Back to Sign In
                        </Text>
                      </Link>
                    </Box>
                  </Stack>
                </form>
              </CardBody>
            </Card>
          </VStack>
        </Container>
      </Box>
    </>
  );
};

export default ForgotPasswordPage;
