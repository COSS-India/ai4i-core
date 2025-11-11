/**
 * Login form component with Chakra UI
 */
import { ViewIcon, ViewOffIcon } from "@chakra-ui/icons";
import {
  Alert,
  AlertDescription,
  AlertIcon,
  AlertTitle,
  Box,
  Button,
  Checkbox,
  FormControl,
  FormLabel,
  Heading,
  IconButton,
  Input,
  InputGroup,
  InputRightElement,
  Link,
  Text,
  VStack,
} from "@chakra-ui/react";
import React, { useState } from "react";
import { useAuth } from "../../hooks/useAuth";
import { LoginRequest } from "../../types/auth";
import LoadingSpinner from "../common/LoadingSpinner";

interface LoginFormProps {
  onSuccess?: () => void;
  onSwitchToRegister?: () => void;
}

const LoginForm: React.FC<LoginFormProps> = ({
  onSuccess,
  onSwitchToRegister,
}) => {
  const { login, isLoading, error, clearError } = useAuth();
  const [formData, setFormData] = useState<LoginRequest>({
    email: "",
    password: "",
    remember_me: false,
  });
  const [showPassword, setShowPassword] = useState(false);
  const [loginAttempted, setLoginAttempted] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  // Clear any initialization errors when component mounts
  React.useEffect(() => {
    clearError();
    setLoginAttempted(false);
    setLoginError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Update loginError when error changes, but only after a login attempt
  React.useEffect(() => {
    if (loginAttempted && error) {
      // Only show login-related errors, not initialization errors
      if (error !== "Failed to initialize authentication") {
        setLoginError(error);
      } else {
        setLoginError(null);
      }
    } else if (!error) {
      setLoginError(null);
    }
  }, [error, loginAttempted]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    clearError();
    setLoginError(null);
    setLoginAttempted(true);

    try {
      await login(formData);
      // Login successful - close modal immediately via onSuccess callback
      // This ensures the modal closes as soon as /me endpoint succeeds
      console.log(
        "LoginForm: Login successful, calling onSuccess to close modal"
      );
      onSuccess?.();
      setLoginAttempted(false);
      setLoginError(null);
    } catch (error) {
      // Error is handled by the hook
      console.error("Login failed:", error);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value, type, checked } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value,
    }));
    // Clear error when user starts typing
    if (loginError) {
      setLoginError(null);
      clearError();
    }
  };

  return (
    <Box maxW="md" mx="auto" p={6}>
      <Heading size="lg" textAlign="center" mb={6} color="gray.800">
        Sign In
      </Heading>

      <form onSubmit={handleSubmit}>
        <VStack spacing={4}>
          {loginError && (
            <Alert status="error" borderRadius="md" width="full">
              <AlertIcon />
              <Box flex="1">
                <AlertTitle fontSize="sm">Login Failed</AlertTitle>
                <AlertDescription fontSize="sm" display="block">
                  {loginError}
                </AlertDescription>
              </Box>
            </Alert>
          )}

          <FormControl isRequired>
            <FormLabel>Email</FormLabel>
            <Input
              type="email"
              name="email"
              value={formData.email}
              onChange={handleChange}
              placeholder="Enter your email"
              size="md"
            />
          </FormControl>

          <FormControl isRequired>
            <FormLabel>Password</FormLabel>
            <InputGroup>
              <Input
                type={showPassword ? "text" : "password"}
                name="password"
                value={formData.password}
                onChange={handleChange}
                placeholder="Enter your password"
                size="md"
                pr="4.5rem"
              />
              <InputRightElement width="4.5rem">
                <IconButton
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  icon={showPassword ? <ViewOffIcon /> : <ViewIcon />}
                  h="1.75rem"
                  size="sm"
                  onClick={() => setShowPassword(!showPassword)}
                  variant="ghost"
                />
              </InputRightElement>
            </InputGroup>
          </FormControl>

          <FormControl>
            <Checkbox
              name="remember_me"
              checked={formData.remember_me}
              onChange={handleChange}
            >
              Remember me
            </Checkbox>
          </FormControl>

          <Button
            type="submit"
            colorScheme="blue"
            size="md"
            width="full"
            isLoading={isLoading}
            loadingText="Signing in..."
            disabled={isLoading}
          >
            {isLoading ? <LoadingSpinner size="sm" /> : "Sign In"}
          </Button>
        </VStack>
      </form>

      <Box mt={6} textAlign="center">
        <Text fontSize="sm" color="gray.600">
          Don&apos;t have an account?{" "}
          <Link
            color="blue.500"
            fontWeight="medium"
            onClick={onSwitchToRegister}
            _hover={{ textDecoration: "underline" }}
            cursor="pointer"
          >
            Sign up
          </Link>
        </Text>
      </Box>
    </Box>
  );
};

export default LoginForm;
