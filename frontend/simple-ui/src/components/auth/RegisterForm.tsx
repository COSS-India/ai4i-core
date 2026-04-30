/**
 * Register form component with Chakra UI
 */
import React, { useState, useEffect, useRef } from 'react';
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
  Select,
  FormErrorMessage,
  useToast,
} from '@chakra-ui/react';
import { ViewIcon, ViewOffIcon } from '@chakra-ui/icons';
import { useAuth } from '../../hooks/useAuth';
import { RegisterRequest } from '../../types/auth';
import LoadingSpinner from '../common/LoadingSpinner';

interface RegisterFormProps {
  onSuccess?: () => void;
  onSwitchToLogin?: () => void;
  onRegisterSuccess?: () => void; // New prop to handle post-registration (switch to login)
  isActive?: boolean; // Prop to indicate if the register tab is currently active
}

const RegisterForm: React.FC<RegisterFormProps> = ({ onSuccess, onSwitchToLogin, onRegisterSuccess, isActive = true }) => {
  const { register, isLoading, error, clearError } = useAuth();
  const toast = useToast();
  const [formData, setFormData] = useState<RegisterRequest>({
    email: '',
    username: '',
    password: '',
    confirm_password: '',
  });

  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const prevIsActiveRef = useRef<boolean>(isActive);

  // Reset form when component becomes active (when switching back to register tab)
  useEffect(() => {
    // Only reset when switching from inactive to active (not on initial mount or re-renders)
    if (isActive && !prevIsActiveRef.current) {
      setFormData({
        email: '',
        username: '',
        password: '',
        confirm_password: '',
      });
      setValidationErrors({});
      setShowPassword(false);
      setShowConfirmPassword(false);
      clearError();
    }
    prevIsActiveRef.current = isActive;
  }, [isActive, clearError]);

  const validateForm = (): boolean => {
    const errors: Record<string, string> = {};

    if (formData.password !== formData.confirm_password) {
      errors.confirm_password = 'Passwords do not match';
    }

    if (formData.password.length < 8) {
      errors.password = 'Password must be at least 8 characters long';
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      errors.email = 'Please enter a valid email address';
    }

    if (!formData.username || formData.username.length < 3) {
      errors.username = 'Username must be at least 3 characters long';
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

    try {
      await register(formData);
      
      // Clear form data after successful registration
      setFormData({
        email: '',
        username: '',
        password: '',
        confirm_password: '',
      });
      setValidationErrors({});
      setShowPassword(false);
      setShowConfirmPassword(false);
      
      // Show success toast
      toast({
        title: "Registration Successful",
        description: "Your account has been created successfully! Please sign in to continue.",
        status: "success",
        duration: 5000,
        isClosable: true,
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
      console.error('Registration failed:', error);
      
      // Extract error message from response
      let errorMessage = 'Registration failed. Please try again.';
      let errorTitle = 'Registration Error';
      
      // Check if error has response data
      if (error?.response) {
        const status = error.response.status;
        const errorData = error.response.data || error.response;
        
        // Extract error message from different possible formats
        if (typeof errorData === 'string') {
          errorMessage = errorData;
        } else if (errorData?.detail) {
          errorMessage = String(errorData.detail);
        } else if (errorData?.message) {
          errorMessage = String(errorData.message);
        } else if (Array.isArray(errorData)) {
          errorMessage = errorData.map((err: any) => 
            err.detail || err.message || String(err)
          ).join(', ');
        } else if (typeof errorData === 'object' && Object.keys(errorData).length > 0) {
          // Try to extract meaningful error from object
          const errorText = errorData.detail || errorData.message || errorData.error;
          errorMessage = errorText ? String(errorText) : JSON.stringify(errorData);
        }
        
        // Provide user-friendly messages based on status code
        if (status === 400) {
          errorTitle = 'Invalid Registration Data';
          if (!errorMessage.includes('already') && !errorMessage.includes('exists')) {
            errorMessage = errorMessage || 'Please check your registration information and try again.';
          }
        } else if (status === 409 || errorMessage.toLowerCase().includes('already exists') || 
                   errorMessage.toLowerCase().includes('already registered') ||
                   errorMessage.toLowerCase().includes('duplicate')) {
          errorTitle = 'Account Already Exists';
          if (errorMessage.toLowerCase().includes('email')) {
            errorMessage = 'An account with this email already exists. Please use a different email or sign in.';
          } else if (errorMessage.toLowerCase().includes('username')) {
            errorMessage = 'This username is already taken. Please choose a different username.';
          } else {
            errorMessage = 'An account with this information already exists. Please sign in instead.';
          }
        } else if (status === 422) {
          errorTitle = 'Validation Error';
          errorMessage = errorMessage || 'Please check that all fields are filled correctly.';
        } else if (status === 500) {
          errorTitle = 'Server Error';
          errorMessage = 'An internal server error occurred. Please try again later.';
        } else if (status === 503) {
          errorTitle = 'Service Unavailable';
          errorMessage = 'The registration service is temporarily unavailable. Please try again later.';
        }
      } else if (error?.message) {
        // Handle Error objects
        const errorMsg = error.message;
        errorMessage = errorMsg;
        
        // Provide user-friendly messages for common error types
        if (errorMsg.includes('timeout') || errorMsg.includes('Timeout')) {
          errorTitle = 'Request Timeout';
          errorMessage = 'The request took too long. Please check your connection and try again.';
        } else if (errorMsg.includes('NetworkError') || errorMsg.includes('Failed to fetch')) {
          errorTitle = 'Network Error';
          errorMessage = 'Unable to connect to the server. Please check your internet connection and try again.';
        } else if (errorMsg.includes('400')) {
          errorTitle = 'Invalid Registration Data';
          errorMessage = 'Please check your registration information and try again.';
        } else if (errorMsg.includes('409')) {
          errorTitle = 'Account Already Exists';
          errorMessage = 'An account with this information already exists. Please sign in instead.';
        }
      }
      
      // Show error toast
      toast({
        title: errorTitle,
        description: errorMessage,
        status: "error",
        duration: 7000,
        isClosable: true,
      });
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value,
    }));

    // Clear validation error for this field
    if (validationErrors[name]) {
      setValidationErrors(prev => {
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
          <FormControl isRequired isInvalid={!!validationErrors.email}>
            <FormLabel>Email</FormLabel>
            <Input
              type="email"
              name="email"
              value={formData.email}
              onChange={handleChange}
              placeholder="Enter your email"
              size="md"
              autoComplete="off"
              data-form-type="other"
            />
            {validationErrors.email && (
              <FormErrorMessage>{validationErrors.email}</FormErrorMessage>
            )}
          </FormControl>

          <FormControl isRequired isInvalid={!!validationErrors.username}>
            <FormLabel>Username</FormLabel>
            <Input
              type="text"
              name="username"
              value={formData.username}
              onChange={handleChange}
              placeholder="Choose a username"
              size="md"
              autoComplete="off"
              data-form-type="other"
            />
            {validationErrors.username && (
              <FormErrorMessage>{validationErrors.username}</FormErrorMessage>
            )}
          </FormControl>

          <FormControl isRequired isInvalid={!!validationErrors.password}>
            <FormLabel>Password</FormLabel>
            <InputGroup>
              <Input
                type={showPassword ? 'text' : 'password'}
                name="password"
                value={formData.password}
                onChange={handleChange}
                placeholder="Create a password (min 8 characters)"
                size="md"
                pr="4.5rem"
                autoComplete="new-password"
                data-form-type="other"
              />
              <InputRightElement width="4.5rem">
                <IconButton
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  icon={showPassword ? <ViewOffIcon /> : <ViewIcon />}
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
          </FormControl>

          <FormControl isRequired isInvalid={!!validationErrors.confirm_password}>
            <FormLabel>Confirm Password</FormLabel>
            <InputGroup>
              <Input
                type={showConfirmPassword ? 'text' : 'password'}
                name="confirm_password"
                value={formData.confirm_password}
                onChange={handleChange}
                placeholder="Confirm your password"
                size="md"
                pr="4.5rem"
                autoComplete="new-password"
                data-form-type="other"
              />
              <InputRightElement width="4.5rem">
                <IconButton
                  aria-label={showConfirmPassword ? 'Hide password' : 'Show password'}
                  icon={showConfirmPassword ? <ViewOffIcon /> : <ViewIcon />}
                  h="1.75rem"
                  size="sm"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  variant="ghost"
                />
              </InputRightElement>
            </InputGroup>
            {validationErrors.confirm_password && (
              <FormErrorMessage>{validationErrors.confirm_password}</FormErrorMessage>
            )}
          </FormControl>

          {/* Phone, timezone, language removed per requirements */}

          <Button
            type="submit"
            colorScheme="blue"
            size="md"
            width="full"
            isLoading={isLoading}
            loadingText="Signing up..."
            disabled={isLoading}
          >
            {isLoading ? <LoadingSpinner size="sm" /> : 'Sign Up'}
          </Button>
        </VStack>
      </form>

      <Box mt={6} textAlign="center">
        <Text fontSize="sm" color="gray.600">
          Already have an account?{' '}
          <Link
            color="blue.500"
            fontWeight="medium"
            onClick={onSwitchToLogin}
            _hover={{ textDecoration: 'underline' }}
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
