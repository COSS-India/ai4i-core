/**
 * Register form component with Chakra UI
 */
import React, { useState } from 'react';
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
} from '@chakra-ui/react';
import { ViewIcon, ViewOffIcon } from '@chakra-ui/icons';
import { useAuth } from '../../hooks/useAuth';
import { RegisterRequest } from '../../types/auth';
import LoadingSpinner from '../common/LoadingSpinner';

interface RegisterFormProps {
  onSuccess?: () => void;
  onSwitchToLogin?: () => void;
  onRegisterSuccess?: () => void; // New prop to handle post-registration (switch to login)
}

const RegisterForm: React.FC<RegisterFormProps> = ({ onSuccess, onSwitchToLogin, onRegisterSuccess }) => {
  const { register, isLoading, error, clearError } = useAuth();
  const [formData, setFormData] = useState<RegisterRequest>({
    email: '',
    username: '',
    password: '',
    confirm_password: '',
    full_name: '',
    phone_number: '',
    timezone: 'UTC',
    language: 'en',
  });

  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

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

    if (formData.username.length < 3) {
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
      // After successful registration, switch to login page
      if (onRegisterSuccess) {
        onRegisterSuccess();
      } else if (onSwitchToLogin) {
        onSwitchToLogin();
      } else {
        onSuccess?.();
      }
    } catch (error) {
      // Error is handled by the hook
      console.error('Registration failed:', error);
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

      <form onSubmit={handleSubmit}>
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
            />
            {validationErrors.username && (
              <FormErrorMessage>{validationErrors.username}</FormErrorMessage>
            )}
          </FormControl>

          <FormControl>
            <FormLabel>Full Name</FormLabel>
            <Input
              type="text"
              name="full_name"
              value={formData.full_name}
              onChange={handleChange}
              placeholder="Enter your full name"
              size="md"
            />
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

          <FormControl>
            <FormLabel>Phone Number</FormLabel>
            <Input
              type="tel"
              name="phone_number"
              value={formData.phone_number}
              onChange={handleChange}
              placeholder="Enter your phone number"
              size="md"
            />
          </FormControl>

          <FormControl>
            <FormLabel>Timezone</FormLabel>
            <Select
              name="timezone"
              value={formData.timezone}
              onChange={handleChange}
              size="md"
            >
              <option value="UTC">UTC</option>
              <option value="America/New_York">Eastern Time</option>
              <option value="America/Chicago">Central Time</option>
              <option value="America/Denver">Mountain Time</option>
              <option value="America/Los_Angeles">Pacific Time</option>
              <option value="Europe/London">London</option>
              <option value="Europe/Paris">Paris</option>
              <option value="Asia/Tokyo">Tokyo</option>
              <option value="Asia/Shanghai">Shanghai</option>
              <option value="Asia/Kolkata">India</option>
            </Select>
          </FormControl>

          <FormControl>
            <FormLabel>Language</FormLabel>
            <Select
              name="language"
              value={formData.language}
              onChange={handleChange}
              size="md"
            >
              <option value="en">English</option>
              <option value="es">Spanish</option>
              <option value="fr">French</option>
              <option value="de">German</option>
              <option value="it">Italian</option>
              <option value="pt">Portuguese</option>
              <option value="ru">Russian</option>
              <option value="ja">Japanese</option>
              <option value="ko">Korean</option>
              <option value="zh">Chinese</option>
              <option value="hi">Hindi</option>
            </Select>
          </FormControl>

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
