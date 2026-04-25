import {
  Alert,
  AlertDescription,
  AlertIcon,
  AlertTitle,
  Box,
  Button,
  Container,
  FormControl,
  FormErrorMessage,
  FormLabel,
  Image,
  Input,
  ListItem,
  Text,
  UnorderedList,
  VStack,
  useColorModeValue,
} from "@chakra-ui/react";
import Head from "next/head";
import { useRouter } from "next/router";
import React, { useEffect, useMemo, useState } from "react";
import { API_BASE_URL } from "../services/api";

type RuleState = {
  minLength: boolean;
  uppercase: boolean;
  lowercase: boolean;
  number: boolean;
  special: boolean;
  match: boolean;
};

const evaluatePasswordRules = (password: string, confirmPassword: string): RuleState => ({
  minLength: password.length >= 8,
  uppercase: /[A-Z]/.test(password),
  lowercase: /[a-z]/.test(password),
  number: /[0-9]/.test(password),
  special: /[!@#$%^&*()_+\-=[\]{}|;:,.<>?]/.test(password),
  match: password.length > 0 && password === confirmPassword,
});

const SetPasswordPage: React.FC = () => {
  const router = useRouter();
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [checkingToken, setCheckingToken] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isCompleted, setIsCompleted] = useState(false);
  const [isTokenUsable, setIsTokenUsable] = useState(true);

  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");
  const pageBg = useColorModeValue("gray.50", "gray.900");

  const token = typeof router.query.token === "string" ? router.query.token : "";
  const rules = useMemo(
    () => evaluatePasswordRules(newPassword, confirmPassword),
    [newPassword, confirmPassword],
  );
  const isPasswordValid = Object.values(rules).every(Boolean);

  const isRuleOkColor = useColorModeValue("green.600", "green.300");
  const isRuleBadColor = useColorModeValue("gray.600", "gray.400");

  useEffect(() => {
    if (!isCompleted) return;
    const timer = setTimeout(() => {
      router.push("/auth");
    }, 2500);
    return () => clearTimeout(timer);
  }, [isCompleted, router]);

  useEffect(() => {
    let cancelled = false;

    const checkTokenStatus = async () => {
      if (!token) {
        if (!cancelled) {
          setError("Invalid setup link. Missing token.");
          setIsTokenUsable(false);
          setCheckingToken(false);
        }
        return;
      }

      try {
        const response = await fetch(
          `${API_BASE_URL}/api/v1/auth/set-password/status?token=${encodeURIComponent(token)}`,
        );
        const payload = await response.json().catch(() => ({}));
        const data = payload?.data || payload;

        if (!response.ok) {
          const message = payload?.detail || payload?.message || "Failed to validate setup link.";
          throw new Error(typeof message === "string" ? message : JSON.stringify(message));
        }

        if (!data?.valid) {
          if (!cancelled) {
            setIsTokenUsable(false);
            setError(data?.message || "This setup link is no longer valid. Please login.");
          }
        }
      } catch (statusError: any) {
        if (!cancelled) {
          setIsTokenUsable(false);
          setError(statusError?.message || "Failed to validate setup link.");
        }
      } finally {
        if (!cancelled) {
          setCheckingToken(false);
        }
      }
    };

    checkTokenStatus();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setSuccess(null);

    if (!token) {
      setError("Invalid setup link. Missing token.");
      return;
    }
    if (!isTokenUsable) {
      setError("Password has already been set. Please login.");
      return;
    }
    if (!isPasswordValid) {
      setError("Please satisfy all password requirements.");
      return;
    }

    setSubmitting(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/auth/set-password`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          token,
          new_password: newPassword,
          confirm_password: confirmPassword,
        }),
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = payload?.detail;
        const msg = typeof detail === "string"
          ? detail
          : detail?.message || payload?.message || "Failed to set password.";
        throw new Error(msg);
      }

      setSuccess("Password setup successfully. You can now login using the portal.");
      setIsCompleted(true);
      setNewPassword("");
      setConfirmPassword("");
    } catch (submitError: any) {
      setError(submitError?.message || "Failed to set password.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <Head>
        <title>Set Password - AI4I Platform</title>
      </Head>
      <Box minH="100vh" bg={pageBg} display="flex" alignItems="center" justifyContent="center" py={8} px={4}>
        <Container maxW="md">
          <Box bg={cardBg} borderColor={cardBorder} borderWidth="1px" borderRadius="lg" p={6} boxShadow="lg">
            <VStack as="form" spacing={4} align="stretch" onSubmit={handleSubmit}>
              <Image
                src="/AI4Inclusion_Logo.svg"
                alt="AI4Inclusion Logo"
                maxH="52px"
                objectFit="contain"
                alignSelf="center"
              />
              <Text fontSize="2xl" fontWeight="bold" textAlign="center">
                Setup Your Password
              </Text>
              <Text color="gray.500" textAlign="center">
                Create a strong password to complete your account setup.
              </Text>

              <FormControl isRequired isInvalid={!!error && !isPasswordValid}>
                <FormLabel>New Password</FormLabel>
                <Input
                  type="password"
                  value={newPassword}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewPassword(e.target.value)}
                  autoComplete="new-password"
                  isDisabled={isCompleted || !isTokenUsable || checkingToken}
                />
              </FormControl>

              <FormControl isRequired isInvalid={!!error && !rules.match}>
                <FormLabel>Confirm Password</FormLabel>
                <Input
                  type="password"
                  value={confirmPassword}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setConfirmPassword(e.target.value)}
                  autoComplete="new-password"
                  isDisabled={isCompleted || !isTokenUsable || checkingToken}
                />
                {!!error && !rules.match && <FormErrorMessage>Passwords must match.</FormErrorMessage>}
              </FormControl>

              <UnorderedList spacing={1} ml={5}>
                <ListItem color={rules.minLength ? isRuleOkColor : isRuleBadColor}>At least 8 characters</ListItem>
                <ListItem color={rules.uppercase ? isRuleOkColor : isRuleBadColor}>At least one uppercase letter</ListItem>
                <ListItem color={rules.lowercase ? isRuleOkColor : isRuleBadColor}>At least one lowercase letter</ListItem>
                <ListItem color={rules.number ? isRuleOkColor : isRuleBadColor}>At least one number</ListItem>
                <ListItem color={rules.special ? isRuleOkColor : isRuleBadColor}>At least one special character</ListItem>
                <ListItem color={rules.match ? isRuleOkColor : isRuleBadColor}>Passwords match</ListItem>
              </UnorderedList>

              {error && (
                <Alert status="error" borderRadius="md">
                  <AlertIcon />
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              {success && (
                <Alert status="success" borderRadius="md">
                  <AlertIcon />
                  <Box>
                    <AlertTitle>Password updated</AlertTitle>
                    <AlertDescription>{success}</AlertDescription>
                    <AlertDescription mt={1}>Redirecting to login...</AlertDescription>
                  </Box>
                </Alert>
              )}

              {isCompleted || !isTokenUsable ? (
                <Button colorScheme="blue" onClick={() => router.push("/auth")}>
                  Go to Login
                </Button>
              ) : (
                <Button
                  type="submit"
                  colorScheme="blue"
                  isLoading={submitting}
                  loadingText="Setting password"
                  isDisabled={!token || checkingToken}
                >
                  Setup Password
                </Button>
              )}
            </VStack>
          </Box>
        </Container>
      </Box>
    </>
  );
};

export default SetPasswordPage;
