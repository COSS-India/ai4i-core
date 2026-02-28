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
  Tooltip,
  VStack,
} from "@chakra-ui/react";
import React, { useState } from "react";
import { useAuth } from "../../hooks/useAuth";
import { LoginRequest } from "../../types/auth";
import LoadingSpinner from "../common/LoadingSpinner";
import { API_BASE_URL } from "../../services/api";

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
        // Ensure error is always a string, not an object
        let errorMessage = 'Login failed';
        if (typeof error === 'string') {
          errorMessage = error;
        } else if (error && typeof error === 'object') {
          // Try to extract error message from various possible formats
          // Type assertion to handle error object properties
          const errorObj = error as any;
          errorMessage = errorObj.message || 
                       errorObj.detail || 
                       errorObj.error || 
                       (errorObj.response?.data?.detail) ||
                       (errorObj.response?.data?.message) ||
                       (typeof errorObj.toString === 'function' && errorObj.toString() !== '[object Object]' ? errorObj.toString() : JSON.stringify(errorObj));
        }
        setLoginError(errorMessage);
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
      // Error is handled by the hook, but log details for debugging
      console.error("LoginForm: Login failed with error:", error);
      if (error instanceof Error) {
        console.error("LoginForm: Error message:", error.message);
        console.error("LoginForm: Error stack:", error.stack);
      }
      // The error state will be updated by the hook, which will trigger the useEffect
      // that updates loginError
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

          <Box width="full" py={2}>
            <Text
              fontSize="sm"
              color="gray.500"
              textAlign="center"
              position="relative"
              _before={{
                content: '""',
                position: "absolute",
                left: 0,
                top: "50%",
                width: "40%",
                height: "1px",
                bg: "gray.300",
              }}
              _after={{
                content: '""',
                position: "absolute",
                right: 0,
                top: "50%",
                width: "40%",
                height: "1px",
                bg: "gray.300",
              }}
            >
              OR
            </Text>
          </Box>

          <Button
            type="button"
            bg="orange.300"
            color="gray.800"
            size="md"
            width="full"
            _hover={{ bg: "orange.400" }}
            _active={{ bg: "orange.500" }}
            onClick={() => {
              const apiBaseUrl =
                API_BASE_URL || (typeof window !== "undefined"
                  ? window.location.origin
                  : "");
              window.location.href = `${apiBaseUrl}/api/v1/auth/oauth2/google/authorize`;
            }}
            leftIcon={
              <svg width="18" height="18" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">
                <g fill="#000" fillRule="evenodd">
                  <path
                    d="M17.64 9.2045c0-.6381-.0573-1.2518-.1636-1.8409H9v3.4814h4.8436c-.2086 1.125-.8427 2.0782-1.7955 2.7164v2.2581h2.9087c1.7023-1.5668 2.6832-3.874 2.6832-6.615z"
                    fill="#4285F4"
                  />
                  <path
                    d="M9 18c2.43 0 4.4673-.806 5.9564-2.1805l-2.9087-2.2581c-.8059.54-1.8368.859-3.0477.859-2.344 0-4.3282-1.5831-5.036-3.7104H.9574v2.3318C2.4382 15.9832 5.4818 18 9 18z"
                    fill="#34A853"
                  />
                  <path
                    d="M3.964 10.71c-.18-.54-.2822-1.1168-.2822-1.71s.1023-1.17.2823-1.71V4.9582H.9573C.3477 6.1732 0 7.5477 0 9s.3477 2.8268.9573 4.0418L3.964 10.71z"
                    fill="#FBBC05"
                  />
                  <path
                    d="M9 3.5795c1.3214 0 2.5077.4541 3.4405 1.3459l2.5813-2.5814C13.4632.8918 11.426 0 9 0 5.4818 0 2.4382 2.0168.9574 4.9582L3.964 7.29C4.6718 5.1627 6.6559 3.5795 9 3.5795z"
                    fill="#EA4335"
                  />
                </g>
              </svg>
            }
          >
            Sign in with Google
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
