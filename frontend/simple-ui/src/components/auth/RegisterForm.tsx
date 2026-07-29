/**
 * Register form component with Chakra UI
 */
import React, { useState, useEffect, useRef } from "react";
import {
  Box,
  Heading,
  FormControl,
  FormLabel,
  Input,
  InputGroup,
  InputRightElement,
  IconButton,
  Button,
  Text,
  VStack,
  Link,
  FormErrorMessage,
  FormHelperText,
} from "@chakra-ui/react";
import { ViewIcon, ViewOffIcon } from "@chakra-ui/icons";
import { useAuth } from "../../hooks/useAuth";
import { RegisterRequest } from "../../types/auth";
import { ApiValidationError } from "../../services/dto/apiValidationError";
import LoadingSpinner from "../common/LoadingSpinner";
import ConsentCheckbox, {
  getConsentValidationError,
} from "../common/ConsentCheckbox";
import { showToast } from "../../utils/toast";
import {
  PASSWORD_POLICY,
  COMMON_ERRORS,
  UI_ERROR_MESSAGES,
} from "../../config/constants";
import PasswordRequirements, {
  getPasswordValidationError,
  passwordPasses,
} from "./password/PasswordRequirements";
import authService from "../../services/authService";

const SIGNUP_EMAIL_ALREADY_EXISTS_MSG =
  "An account with this email already exists. Please use a different email or sign in.";

const SIGNUP_EMAIL_INVALID_MSG = "Please enter a valid email address";

interface RegisterFormProps {
  onSuccess?: () => void;
  onSwitchToLogin?: () => void;
  onRegisterSuccess?: () => void; // New prop to handle post-registration (switch to login)
  isActive?: boolean; // Prop to indicate if the register tab is currently active
}

const RegisterForm: React.FC<RegisterFormProps> = ({
  onSuccess,
  onSwitchToLogin,
  onRegisterSuccess,
  isActive = true,
}) => {
  const { register, isLoading, clearError } = useAuth();
  const [formData, setFormData] = useState<RegisterRequest>({
    full_name: "",
    email: "",
    password: "",
    confirm_password: "",
  });

  const [validationErrors, setValidationErrors] = useState<
    Record<string, string>
  >({});
  const [consentAccepted, setConsentAccepted] = useState(false);
  const [isCheckingEmail, setIsCheckingEmail] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const prevIsActiveRef = useRef<boolean>(isActive);
  const emailCheckRequestIdRef = useRef(0);

  // Reset form when component becomes active (when switching back to register tab)
  useEffect(() => {
    // Only reset when switching from inactive to active (not on initial mount or re-renders)
    if (isActive && !prevIsActiveRef.current) {
      setFormData({
        full_name: "",
        email: "",
        password: "",
        confirm_password: "",
      });
      setValidationErrors({});
      setIsCheckingEmail(false);
      emailCheckRequestIdRef.current += 1;
      setShowPassword(false);
      setShowConfirmPassword(false);
      clearError();
    }
    prevIsActiveRef.current = isActive;
  }, [isActive, clearError]);

  const validateEmailFormat = (email: string): string | undefined => {
    if (!/^[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+$/.test(email.trim())) {
      return SIGNUP_EMAIL_INVALID_MSG;
    }
    return undefined;
  };

  const checkEmailAvailability = async (
    email: string,
  ): Promise<string | undefined> => {
    const formatError = validateEmailFormat(email);
    if (formatError) return formatError;

    const requestId = ++emailCheckRequestIdRef.current;
    setIsCheckingEmail(true);
    try {
      const exists = await authService.checkEmailExists(email, {
        withAuth: false,
      });
      if (requestId !== emailCheckRequestIdRef.current) return undefined;
      if (exists) return SIGNUP_EMAIL_ALREADY_EXISTS_MSG;
      return undefined;
    } catch {
      if (requestId !== emailCheckRequestIdRef.current) return undefined;
      return undefined;
    } finally {
      if (requestId === emailCheckRequestIdRef.current) {
        setIsCheckingEmail(false);
      }
    }
  };

  const handleEmailBlur = async () => {
    const trimmed = formData.email.trim();
    if (!trimmed) return;

    const error = await checkEmailAvailability(trimmed);
    if (error) {
      setValidationErrors((prev) => ({ ...prev, email: error }));
    } else {
      setValidationErrors((prev) => {
        if (!prev.email) return prev;
        const next = { ...prev };
        delete next.email;
        return next;
      });
    }
  };

  const validateForm = (): boolean => {
    const errors: Record<string, string> = {};

    const trimmedFullName = formData.full_name?.trim() ?? "";
    if (!trimmedFullName) {
      errors.full_name = "Full name is required";
    } else if (trimmedFullName.length < 2) {
      errors.full_name = "Full name must be at least 2 characters";
    } else if (trimmedFullName.length > 100) {
      errors.full_name = "Full name must be at most 100 characters";
    }

    if (formData.password !== formData.confirm_password) {
      errors.confirm_password = "Passwords do not match";
    }

    const consentError = getConsentValidationError(consentAccepted);
    if (consentError) {
      errors.consent = consentError;
    }

    const passwordError = getPasswordValidationError(formData.password);
    if (passwordError) {
      errors.password = passwordError;
    }

    const emailFormatError = validateEmailFormat(formData.email);
    if (emailFormatError) {
      errors.email = emailFormatError;
    } else if (validationErrors.email === SIGNUP_EMAIL_ALREADY_EXISTS_MSG) {
      errors.email = SIGNUP_EMAIL_ALREADY_EXISTS_MSG;
    }

    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    clearError();

    if (!validateForm()) {
      return;
    }

    const emailError = await checkEmailAvailability(formData.email);
    if (emailError) {
      setValidationErrors((prev) => ({ ...prev, email: emailError }));
      return;
    }

    try {
      await register({
        ...formData,
        full_name: (formData.full_name ?? "").trim(),
      });

      // Clear form data after successful registration
      setFormData({
        full_name: "",
        email: "",
        password: "",
        confirm_password: "",
      });
      setValidationErrors({});
      setShowPassword(false);
      setShowConfirmPassword(false);
      setConsentAccepted(false);

      // Show success toast — user must verify email before sign-in works.
      showToast({
        type: "success",
        message:
          "We sent a verification link to your inbox. Click the link to activate your account, then sign in.",
      });

      // After successful registration, switch to login page
      if (onRegisterSuccess) {
        onRegisterSuccess();
      } else if (onSwitchToLogin) {
        onSwitchToLogin();
      } else {
        onSuccess?.();
      }
    } catch (error: any) {
      console.error("Registration failed:", error);

      // Extract error message from response
      let errorMessage: string = UI_ERROR_MESSAGES.REGISTRATION_FAILED;
      let errorTitle = "Registration Error";

      if (error instanceof ApiValidationError) {
        errorTitle = "Registration Error";
        errorMessage =
          "We could not confirm your registration. If you received a verification email, use that link to activate your account; otherwise try again or sign in.";
      } else if (error?.response) {
        const status = error?.response?.status;
        const errorData = error?.response?.data ?? error?.response;

        // Extract error message from different possible formats
        if (typeof errorData === "string") {
          errorMessage = errorData;
        } else if (errorData?.detail) {
          errorMessage = String(errorData.detail);
        } else if (errorData?.message) {
          errorMessage = String(errorData.message);
        } else if (Array.isArray(errorData)) {
          errorMessage = errorData
            .map((err: any) => err.detail || err.message || String(err))
            .join(", ");
        } else if (
          typeof errorData === "object" &&
          Object.keys(errorData).length > 0
        ) {
          // Try to extract meaningful error from object
          const errorText =
            errorData.detail || errorData.message || errorData.error;
          errorMessage = errorText
            ? String(errorText)
            : JSON.stringify(errorData);
        }

        // Provide user-friendly messages based on status code
        if (status === 400) {
          errorTitle = "Invalid Registration Data";
          if (
            !errorMessage.includes("already") &&
            !errorMessage.includes("exists")
          ) {
            errorMessage =
              errorMessage ||
              "Please check your registration information and try again.";
          }
        } else if (
          status === 409 ||
          errorMessage.toLowerCase().includes("already exists") ||
          errorMessage.toLowerCase().includes("already registered") ||
          errorMessage.toLowerCase().includes("duplicate")
        ) {
          errorTitle = "Account Already Exists";
          if (errorMessage.toLowerCase().includes("email")) {
            errorMessage = SIGNUP_EMAIL_ALREADY_EXISTS_MSG;
          } else if (errorMessage.toLowerCase().includes("username")) {
            errorMessage =
              "This username is already taken. Please choose a different username.";
          } else {
            errorMessage =
              "An account with this information already exists. Please sign in instead.";
          }
        } else if (status === 422) {
          errorTitle = "Validation Error";
          errorMessage =
            errorMessage ||
            "Please check that all fields are filled correctly.";
        } else if (status === 500) {
          errorTitle = "Server Error";
          errorMessage = COMMON_ERRORS.INTERNAL_SERVER_ERROR.description;
        } else if (status === 503) {
          errorTitle = "Service Unavailable";
          errorMessage = COMMON_ERRORS.SERVICE_MAINTENANCE.description;
        }
      } else if (error?.message) {
        // Handle Error objects
        const errorMsg = error.message;
        errorMessage = errorMsg;

        // Provide user-friendly messages for common error types
        if (errorMsg.includes("timeout") || errorMsg.includes("Timeout")) {
          errorTitle = "Request Timeout";
          errorMessage =
            "The request took too long. Please check your connection and try again.";
        } else if (
          errorMsg.includes("NetworkError") ||
          errorMsg.includes("Failed to fetch")
        ) {
          errorTitle = "Network Error";
          errorMessage =
            "Unable to connect to the server. Please check your internet connection and try again.";
        } else if (errorMsg.includes("400")) {
          errorTitle = "Invalid Registration Data";
          errorMessage =
            "Please check your registration information and try again.";
        } else if (errorMsg.includes("409")) {
          errorTitle = "Account Already Exists";
          errorMessage =
            "An account with this information already exists. Please sign in instead.";
        }
      }

      // Show error toast
      showToast({ type: "error", message: errorMessage });
    }
  };

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>,
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));

    if (name === "email") {
      emailCheckRequestIdRef.current += 1;
      setIsCheckingEmail(false);
    }

    // Clear validation error for this field
    if (validationErrors[name]) {
      setValidationErrors((prev) => {
        const newErrors = { ...prev };
        delete newErrors[name];
        return newErrors;
      });
    }
  };

  return (
    <Box maxW="md" mx="auto" p={6}>
      <Heading size="lg" textAlign="center" mb={6} color="gray.800">
        Sign Up
      </Heading>

      <form onSubmit={handleSubmit} autoComplete="off">
        <VStack spacing={4}>
          <FormControl isRequired isInvalid={!!validationErrors.full_name}>
            <FormLabel>Full Name</FormLabel>
            <Input
              type="text"
              name="full_name"
              value={formData.full_name}
              onChange={handleChange}
              placeholder="Enter your full name"
              size="md"
              autoComplete="name"
              data-form-type="other"
              maxLength={100}
            />
            {validationErrors.full_name && (
              <FormErrorMessage>{validationErrors.full_name}</FormErrorMessage>
            )}
          </FormControl>

          <FormControl isRequired isInvalid={!!validationErrors.email}>
            <FormLabel>Email</FormLabel>
            <Input
              type="email"
              name="email"
              value={formData.email}
              onChange={handleChange}
              onBlur={handleEmailBlur}
              placeholder="Enter your email"
              size="md"
              autoComplete="off"
              data-form-type="other"
            />
            {isCheckingEmail && !validationErrors.email && (
              <FormHelperText color="gray.500">
                Checking if email exists…
              </FormHelperText>
            )}
            {validationErrors.email && (
              <FormErrorMessage>{validationErrors.email}</FormErrorMessage>
            )}
          </FormControl>

          <FormControl isRequired isInvalid={!!validationErrors.password}>
            <FormLabel>Password</FormLabel>
            <InputGroup>
              <Input
                type={showPassword ? "text" : "password"}
                name="password"
                value={formData.password}
                onChange={handleChange}
                placeholder="Create a password"
                size="md"
                pr="4.5rem"
                autoComplete="new-password"
                data-form-type="other"
                minLength={PASSWORD_POLICY.MIN_LENGTH}
                maxLength={PASSWORD_POLICY.MAX_LENGTH}
              />
              <InputRightElement width="4.5rem">
                <IconButton
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  icon={showPassword ? <ViewIcon /> : <ViewOffIcon />}
                  h="1.75rem"
                  size="sm"
                  onClick={() => setShowPassword(!showPassword)}
                  variant="ghost"
                />
              </InputRightElement>
            </InputGroup>
            {validationErrors.password && (
              <FormErrorMessage>{validationErrors.password}</FormErrorMessage>
            )}
            {/* Live policy checklist — mirrors backend rules exactly */}
            <PasswordRequirements password={formData.password} compact />
          </FormControl>

          <FormControl
            isRequired
            isInvalid={!!validationErrors.confirm_password}
          >
            <FormLabel>Confirm Password</FormLabel>
            <InputGroup>
              <Input
                type={showConfirmPassword ? "text" : "password"}
                name="confirm_password"
                value={formData.confirm_password}
                onChange={handleChange}
                placeholder="Confirm your password"
                size="md"
                pr="4.5rem"
                autoComplete="new-password"
                data-form-type="other"
                minLength={PASSWORD_POLICY.MIN_LENGTH}
                maxLength={PASSWORD_POLICY.MAX_LENGTH}
              />
              <InputRightElement width="4.5rem">
                <IconButton
                  aria-label={
                    showConfirmPassword ? "Hide password" : "Show password"
                  }
                  icon={showConfirmPassword ? <ViewIcon /> : <ViewOffIcon />}
                  h="1.75rem"
                  size="sm"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  variant="ghost"
                />
              </InputRightElement>
            </InputGroup>
            {validationErrors.confirm_password && (
              <FormErrorMessage>
                {validationErrors.confirm_password}
              </FormErrorMessage>
            )}
          </FormControl>

          {/* Phone, timezone, language removed per requirements */}

          <ConsentCheckbox
            isChecked={consentAccepted}
            onChange={(checked) => {
              setConsentAccepted(checked);
              if (checked) {
                setValidationErrors((prev) => {
                  if (!prev.consent) return prev;
                  const next = { ...prev };
                  delete next.consent;
                  return next;
                });
              }
            }}
            error={validationErrors.consent}
          />

          <Button
            type="submit"
            colorScheme="blue"
            size="md"
            width="full"
            isLoading={isLoading}
            loadingText="Signing up..."
            disabled={
              isLoading ||
              isCheckingEmail ||
              !passwordPasses(formData.password) ||
              formData.password !== formData.confirm_password ||
              !consentAccepted
            }
          >
            {isLoading ? <LoadingSpinner size="sm" /> : "Sign Up"}
          </Button>
        </VStack>
      </form>

      <Box mt={6} textAlign="center">
        <Text fontSize="sm" color="gray.600">
          Already have an account?{" "}
          <Link
            color="blue.500"
            fontWeight="medium"
            onClick={onSwitchToLogin}
            _hover={{ textDecoration: "underline" }}
            cursor="pointer"
          >
            Sign in
          </Link>
        </Text>
      </Box>
    </Box>
  );
};

export default RegisterForm;
