// Profile page displaying user information and API key with edit functionality

import {
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  FormControl,
  FormLabel,
  FormErrorMessage,
  Heading,
  Input,
  InputGroup,
  InputRightElement,
  IconButton,
  Text,
  VStack,
  HStack,
  useColorModeValue,
  Spinner,
  Center,
  Alert,
  AlertIcon,
  AlertDescription,
  Select,
  useToast,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Badge,
  TableContainer,
  Checkbox,
  CheckboxGroup,
  SimpleGrid,
} from "@chakra-ui/react";
import { ViewIcon, ViewOffIcon, CopyIcon } from "@chakra-ui/icons";
import { FiEdit2, FiCheck, FiX } from "react-icons/fi";
import Head from "next/head";
import React, { useState, useEffect } from "react";
import { useRouter } from "next/router";
import ContentLayout from "../components/common/ContentLayout";
import { useAuth } from "../hooks/useAuth";
import { useApiKey } from "../hooks/useApiKey";
import { User, UserUpdateRequest, Permission, APIKeyResponse } from "../types/auth";
import roleService, { Role, UserRole } from "../services/roleService";
import authService from "../services/authService";

const ProfilePage: React.FC = () => {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading, updateUser } = useAuth();
  const { apiKey, getApiKey, setApiKey } = useApiKey();
  const [showApiKey, setShowApiKey] = useState(false);
  const [isEditingUser, setIsEditingUser] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [userFormData, setUserFormData] = useState<UserUpdateRequest>({
    full_name: "",
    phone_number: "",
    timezone: "UTC",
    language: "en",
    preferences: {},
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const toast = useToast();
  
  // Role management state
  const [roles, setRoles] = useState<Role[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [isLoadingUsers, setIsLoadingUsers] = useState(false);
  const [selectedUser, setSelectedUser] = useState<{ id: number; email: string; username: string } | null>(null);
  const [selectedUserRoles, setSelectedUserRoles] = useState<string[]>([]);
  const [selectedRole, setSelectedRole] = useState<string>("");
  const [isLoadingRoles, setIsLoadingRoles] = useState(false);
  const [isLoadingUserRoles, setIsLoadingUserRoles] = useState(false);
  const [isAssigningRole, setIsAssigningRole] = useState(false);
  const [isRemovingRole, setIsRemovingRole] = useState(false);
  
  // Permissions management state
  const [permissions, setPermissions] = useState<string[]>([]);
  const [isLoadingPermissions, setIsLoadingPermissions] = useState(false);
  const [selectedUserForPermissions, setSelectedUserForPermissions] = useState<{ id: number; email: string; username: string } | null>(null);
  const [selectedUserPermissions, setSelectedUserPermissions] = useState<string[]>([]);
  const [isLoadingUserPermissions, setIsLoadingUserPermissions] = useState(false);
  const [isAssigningPermission, setIsAssigningPermission] = useState(false);
  
  // API Key creation for user (in Permissions tab)
  const [apiKeyForUser, setApiKeyForUser] = useState({
    key_name: "",
    permissions: [] as string[],
    expires_days: 30,
  });
  const [selectedPermissionsForUser, setSelectedPermissionsForUser] = useState<string[]>([]);
  const [isCreatingApiKeyForUser, setIsCreatingApiKeyForUser] = useState(false);
  
  // API Key management state (for all users)
  const [apiKeys, setApiKeys] = useState<APIKeyResponse[]>([]);
  const [isLoadingApiKeys, setIsLoadingApiKeys] = useState(false);
  const [isCreatingApiKey, setIsCreatingApiKey] = useState(false);
  const [newApiKey, setNewApiKey] = useState({
    key_name: "",
    permissions: [] as string[],
    expires_days: 30,
  });
  const [selectedPermissionsForApiKey, setSelectedPermissionsForApiKey] = useState<string[]>([]);
  
  // State for fetching API key when tab is clicked
  const [isFetchingApiKey, setIsFetchingApiKey] = useState(false);
  const [activeTabIndex, setActiveTabIndex] = useState(0);
  
  // Load persisted selected API key ID from localStorage on mount
  const [selectedApiKeyId, setSelectedApiKeyId] = useState<number | null>(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('selected_api_key_id');
      return stored ? parseInt(stored, 10) : null;
    }
    return null;
  });
  
  // Persist selected API key ID to localStorage whenever it changes
  useEffect(() => {
    if (typeof window !== 'undefined') {
      if (selectedApiKeyId !== null) {
        localStorage.setItem('selected_api_key_id', selectedApiKeyId.toString());
      } else {
        localStorage.removeItem('selected_api_key_id');
      }
    }
  }, [selectedApiKeyId]);
  
  // Effect to find and populate API key based on selected permissions (only if no key is currently selected)
  useEffect(() => {
    // Only auto-select if no API key is currently selected and we have matching permissions
    if (selectedApiKeyId === null && selectedPermissionsForUser.length > 0 && apiKeys.length > 0) {
      // Find API key that matches the selected permissions exactly
      const matchingKey = apiKeys.find((key) => {
        if (key.permissions.length !== selectedPermissionsForUser.length) {
          return false;
        }
        // Check if all selected permissions are in the key's permissions
        const sortedSelected = [...selectedPermissionsForUser].sort();
        const sortedKeyPerms = [...key.permissions].sort();
        return JSON.stringify(sortedSelected) === JSON.stringify(sortedKeyPerms);
      });
      
      if (matchingKey) {
        // Set the selected API key ID to highlight it in the list
        setSelectedApiKeyId(matchingKey.id);
        
        if (matchingKey.key_value) {
          // If key_value is available (only on creation), set it
          setApiKey(matchingKey.key_value);
          toast({
            title: "API Key Found",
            description: `API key "${matchingKey.key_name}" matches the selected permissions`,
            status: "info",
            duration: 3000,
            isClosable: true,
          });
        } else {
          // If key exists but key_value is not available, show a message
          toast({
            title: "API Key Found",
            description: `API key "${matchingKey.key_name}" matches the selected permissions, but the key value is not available (only shown once on creation)`,
            status: "info",
            duration: 4000,
            isClosable: true,
          });
        }
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPermissionsForUser, apiKeys, selectedApiKeyId]);
  
  // Load API key value when a persisted selection is restored
  useEffect(() => {
    if (selectedApiKeyId !== null && apiKeys.length > 0) {
      const selectedKey = apiKeys.find(key => key.id === selectedApiKeyId);
      if (selectedKey && selectedKey.key_value) {
        // If the selected key has a value, set it
        setApiKey(selectedKey.key_value);
      }
    }
  }, [selectedApiKeyId, apiKeys, setApiKey]);

  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");
  const inputReadOnlyBg = useColorModeValue("gray.50", "gray.700");

  // Initialize form data when user data is available
  useEffect(() => {
    if (user) {
      setUserFormData({
        full_name: user.full_name || "",
        phone_number: user.phone_number || "",
        timezone: user.timezone || "UTC",
        language: user.language || "en",
        preferences: user.preferences || {},
      });
     
    }
  }, [user]);

  // Redirect to home if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/");
    }
  }, [isAuthenticated, authLoading, router]);

  // Fetch all users (Admin only)
  useEffect(() => {
    const fetchUsers = async () => {
      // Only fetch if user is authenticated, not loading, and is an ADMIN
      if (!isAuthenticated || authLoading || !user) return;
      
      // Check if user is admin or superuser
      const isAdmin = user?.roles?.includes('ADMIN') || user?.is_superuser;
      if (!isAdmin) {
        // Not an admin, don't fetch users
        return;
      }
      
      setIsLoadingUsers(true);
      try {
        const usersList = await authService.getAllUsers();
        console.log("u",usersList);
        
        setUsers(usersList);
      } catch (error) {
        console.error("Failed to fetch users:", error);
        toast({
          title: "Error",
          description: error instanceof Error ? error.message : "Failed to load users. Only administrators can view users.",
          status: "error",
          duration: 5000,
          isClosable: true,
        });
      } finally {
        setIsLoadingUsers(false);
      }
    };

    fetchUsers();
  }, [isAuthenticated, authLoading, toast, user]);

  const handleCopyApiKey = () => {
    const key = getApiKey();
    if (key) {
      navigator.clipboard.writeText(key);
      toast({
        title: "API Key Copied",
        description: "API key has been copied to clipboard",
        status: "success",
        duration: 2000,
        isClosable: true,
      });
    }
  };

  const handleEditUser = () => {
    setIsEditingUser(true);
    setErrors({});
  };

  const handleCancelEdit = () => {
    setIsEditingUser(false);
    setErrors({});
    // Reset form data to original user data
    if (user) {
      setUserFormData({
        full_name: user.full_name || "",
        phone_number: user.phone_number || "",
        timezone: user.timezone || "UTC",
        language: user.language || "en",
        preferences: user.preferences || {},
      });
    }
  };

  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (userFormData.phone_number && userFormData.phone_number.length > 0) {
      // Basic phone validation (allows numbers, spaces, dashes, parentheses, plus)
      const phoneRegex = /^[\d\s\-+()]+$/;
      if (!phoneRegex.test(userFormData.phone_number)) {
        newErrors.phone_number = "Invalid phone number format";
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSaveUser = async () => {
    if (!validateForm()) {
      return;
    }

    setIsSaving(true);
    try {
      // Prepare update data matching API structure exactly
      // API expects: full_name, phone_number, timezone, language, preferences
      const updateData: UserUpdateRequest = {
        full_name: userFormData.full_name?.trim() || "",
        phone_number: userFormData.phone_number?.trim() || "",
        timezone: userFormData.timezone || "UTC",
        language: userFormData.language || "en",
        preferences: userFormData.preferences || {},
      };

      const updatedUser = await updateUser(updateData as Partial<User>);
      toast({
        title: "Profile Updated",
        description: "Your profile has been updated successfully",
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      setIsEditingUser(false);
      setErrors({});
    } catch (error) {
      toast({
        title: "Update Failed",
        description: error instanceof Error ? error.message : "Failed to update profile",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleInputChange = (field: keyof UserUpdateRequest, value: string | Record<string, any>) => {
    setUserFormData((prev) => ({
      ...prev,
      [field]: value,
    }));
    // Clear error for this field when user starts typing
    if (errors[field]) {
      setErrors((prev) => {
        const newErrors = { ...prev };
        delete newErrors[field];
        return newErrors;
      });
    }
  };

  const maskedApiKey = apiKey ? "****" + apiKey.slice(-4) : "";

  // Function to fetch API keys from the API
  const handleFetchApiKeys = async () => {
    console.log('Profile: Fetching API keys from /api/v1/auth/api-keys');
    setIsFetchingApiKey(true);
    setIsLoadingApiKeys(true);
    try {
      const fetchedApiKeys = await authService.listApiKeys();
      console.log('Profile: API keys fetched successfully:', fetchedApiKeys);
      setApiKeys(fetchedApiKeys);
      
      // If there's at least one API key, use the first one (or most recent)
      if (fetchedApiKeys.length > 0) {
        // Find the most recent active API key
        const activeKey = fetchedApiKeys
          .filter(key => key.is_active)
          .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0];
        
        if (activeKey && activeKey.key_value) {
          // If key_value is available (only on creation), store it
          setApiKey(activeKey.key_value);
        }
      }
      
      toast({
        title: "API Keys Loaded",
        description: `Found ${fetchedApiKeys.length} API key(s)`,
        status: "success",
        duration: 2000,
        isClosable: true,
      });
    } catch (error) {
      console.error("Failed to fetch API keys:", error);
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to load API keys",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsFetchingApiKey(false);
      setIsLoadingApiKeys(false);
    }
  };

  // Common timezones
  const timezones = [
    "UTC",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Asia/Kolkata",
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Australia/Sydney",
  ];

  // Common languages
  const languages = [
    { value: "en", label: "English" },
    { value: "hi", label: "Hindi" },
    { value: "ta", label: "Tamil" },
    { value: "te", label: "Telugu" },
    { value: "kn", label: "Kannada" },
    { value: "ml", label: "Malayalam" },
    { value: "bn", label: "Bengali" },
    { value: "gu", label: "Gujarati" },
    { value: "mr", label: "Marathi" },
    { value: "pa", label: "Punjabi" },
  ];

  // Show loading spinner while checking authentication
  if (authLoading) {
    return (
      <ContentLayout>
        <Center h="400px">
          <Spinner size="xl" color="orange.500" />
        </Center>
      </ContentLayout>
    );
  }

  // Show message if not authenticated (will redirect)
  if (!isAuthenticated || !user) {
    return (
      <ContentLayout>
        <Alert status="warning">
          <AlertIcon />
          <AlertDescription>Please log in to view your profile.</AlertDescription>
        </Alert>
      </ContentLayout>
    );
  }

  return (
    <>
      <Head>
        <title>Profile - AI4I Platform</title>
        <meta name="description" content="User profile and API key management" />
      </Head>

      <ContentLayout>
        <Box maxW="4xl" mx="auto" py={8} px={4}>
          <Heading size="xl" mb={8} color="gray.800">
            Profile
          </Heading>

          <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px">
            <Tabs 
              colorScheme="blue" 
              variant="enclosed"
              index={activeTabIndex}
              onChange={(index) => {
                setActiveTabIndex(index);
                // Calculate tab indices
                // Tabs: 0=User Details, 1=Organization, 2=API Key, 3=Roles (if admin), 4=Permissions (if admin)
                const apiKeyTabIndex = 2;
                const permissionsTabIndex = (user?.roles?.includes('ADMIN') || user?.is_superuser) ? 4 : -1;
                console.log('Profile: Tab changed to index', index, 'API Key tab index is', apiKeyTabIndex, 'Permissions tab index is', permissionsTabIndex);
                // When API Key tab is clicked, fetch API keys
                if (index === apiKeyTabIndex) {
                  console.log('Profile: API Key tab clicked, calling handleFetchApiKeys');
                  handleFetchApiKeys();
                }
                // When Permissions tab is clicked, also fetch API keys for matching
                if (index === permissionsTabIndex && apiKeys.length === 0) {
                  console.log('Profile: Permissions tab clicked, fetching API keys for matching');
                  handleFetchApiKeys();
                }
              }}
            >
              <TabList>
                <Tab fontWeight="semibold">User Details</Tab>
                <Tab fontWeight="semibold">Organization</Tab>
                <Tab fontWeight="semibold">API Key</Tab>
                {(user?.roles?.includes('ADMIN') || user?.is_superuser) && (
                  <>
                    <Tab fontWeight="semibold">Roles</Tab>
                    <Tab fontWeight="semibold">Permissions</Tab>
                  </>
                )}
              </TabList>

              <TabPanels>
                {/* User Details Tab */}
                <TabPanel px={0} pt={6}>
                  <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
                    <CardHeader>
                      <HStack justify="space-between">
                        <Heading size="md" color="gray.700">
                          User Details
                        </Heading>
                        {!isEditingUser ? (
                          <Button
                            leftIcon={<FiEdit2 />}
                            size="sm"
                            colorScheme="blue"
                            variant="outline"
                            onClick={handleEditUser}
                          >
                            Edit
                          </Button>
                        ) : (
                          <HStack>
                            <Button
                              leftIcon={<FiCheck />}
                              size="sm"
                              colorScheme="green"
                              onClick={handleSaveUser}
                              isLoading={isSaving}
                              loadingText="Saving..."
                            >
                              Save
                            </Button>
                            <Button
                              leftIcon={<FiX />}
                              size="sm"
                              variant="outline"
                              onClick={handleCancelEdit}
                              isDisabled={isSaving}
                            >
                              Cancel
                            </Button>
                          </HStack>
                        )}
                      </HStack>
                    </CardHeader>
                    <CardBody>
                <VStack spacing={4} align="stretch">
                  <FormControl>
                    <FormLabel fontWeight="semibold">Full Name</FormLabel>
                    <Input
                      value={isEditingUser ? (userFormData.full_name || "") : (user.full_name || user.username || "N/A")}
                      isReadOnly={!isEditingUser}
                      onChange={(e) => handleInputChange("full_name", e.target.value)}
                      bg={isEditingUser ? "white" : inputReadOnlyBg}
                      placeholder="Enter your full name"
                    />
                  </FormControl>

                  <FormControl>
                    <FormLabel fontWeight="semibold">Username</FormLabel>
                    <Input
                      value={user.username || "N/A"}
                      isReadOnly
                      bg={inputReadOnlyBg}
                    />
                    <Text fontSize="xs" color="gray.500" mt={1}>
                      Username cannot be changed
                    </Text>
                  </FormControl>

                  <FormControl>
                    <FormLabel fontWeight="semibold">Email</FormLabel>
                    <Input
                      value={user.email || "N/A"}
                      isReadOnly
                      bg={inputReadOnlyBg}
                    />
                    <Text fontSize="xs" color="gray.500" mt={1}>
                      Email cannot be changed
                    </Text>
                  </FormControl>

                  <FormControl isInvalid={!!errors.phone_number}>
                    <FormLabel fontWeight="semibold">Phone Number</FormLabel>
                    <Input
                      value={isEditingUser ? (userFormData.phone_number || "") : (user.phone_number || "")}
                      isReadOnly={!isEditingUser}
                      onChange={(e) => handleInputChange("phone_number", e.target.value)}
                      bg={isEditingUser ? "white" : inputReadOnlyBg}
                      placeholder="Enter your phone number"
                    />
                    {errors.phone_number && (
                      <FormErrorMessage>{errors.phone_number}</FormErrorMessage>
                    )}
                  </FormControl>

                  <HStack spacing={4}>
                    <FormControl flex={1}>
                      <FormLabel fontWeight="semibold">Timezone</FormLabel>
                      {isEditingUser ? (
                        <Select
                          value={userFormData.timezone || "UTC"}
                          onChange={(e) => handleInputChange("timezone", e.target.value)}
                          bg="white"
                        >
                          {timezones.map((tz) => (
                            <option key={tz} value={tz}>
                              {tz}
                            </option>
                          ))}
                        </Select>
                      ) : (
                        <Input
                          value={user.timezone || "N/A"}
                          isReadOnly
                          bg={inputReadOnlyBg}
                        />
                      )}
                    </FormControl>

                    <FormControl flex={1}>
                      <FormLabel fontWeight="semibold">Language</FormLabel>
                      {isEditingUser ? (
                        <Select
                          value={userFormData.language || "en"}
                          onChange={(e) => handleInputChange("language", e.target.value)}
                          bg="white"
                        >
                          {languages.map((lang) => (
                            <option key={lang.value} value={lang.value}>
                              {lang.label}
                            </option>
                          ))}
                        </Select>
                      ) : (
                        <Input
                          value={languages.find((l) => l.value === user.language)?.label || user.language || "N/A"}
                          isReadOnly
                          bg={inputReadOnlyBg}
                        />
                      )}
                    </FormControl>
                  </HStack>

                  <HStack spacing={4}>
                    <FormControl flex={1}>
                      <FormLabel fontWeight="semibold">Status</FormLabel>
                      <Input
                        value={user.is_active ? "Active" : "Inactive"}
                        isReadOnly
                        bg={inputReadOnlyBg}
                      />
                    </FormControl>

                    <FormControl flex={1}>
                      <FormLabel fontWeight="semibold">Verified</FormLabel>
                      <Input
                        value={user.is_verified ? "Yes" : "No"}
                        isReadOnly
                        bg={inputReadOnlyBg}
                      />
                    </FormControl>
                  </HStack>

                  {user.created_at && (
                    <FormControl>
                      <FormLabel fontWeight="semibold">Member Since</FormLabel>
                      <Input
                        value={new Date(user.created_at).toLocaleDateString()}
                        isReadOnly
                        bg={inputReadOnlyBg}
                      />
                    </FormControl>
                  )}
                    </VStack>
                  </CardBody>
                </Card>
                </TabPanel>

                {/* Organization Details Tab */}
                <TabPanel px={0} pt={6}>
                  <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
                    <CardHeader>
                      <Heading size="md" color="gray.700">
                        Organization Details
                      </Heading>
                    </CardHeader>
                    <CardBody>
                <VStack spacing={4} align="stretch">
                  <Alert status="info" borderRadius="md">
                    <AlertIcon />
                    <AlertDescription>
                      Organization management features are coming soon. You will be able to view and manage your organization details here.
                    </AlertDescription>
                  </Alert>
                  
                  <FormControl>
                    <FormLabel fontWeight="semibold">Organization Name</FormLabel>
                    <Input
                      value="Not Available"
                      isReadOnly
                      bg={inputReadOnlyBg}
                    />
                  </FormControl>

                  <FormControl>
                    <FormLabel fontWeight="semibold">Organization ID</FormLabel>
                    <Input
                      value="Not Available"
                      isReadOnly
                      bg={inputReadOnlyBg}
                    />
                  </FormControl>

                  <FormControl>
                    <FormLabel fontWeight="semibold">Role</FormLabel>
                    <Input
                      value="Not Available"
                      isReadOnly
                      bg={inputReadOnlyBg}
                    />
                  </FormControl>
                    </VStack>
                  </CardBody>
                </Card>
                </TabPanel>

                {/* API Key Tab */}
                <TabPanel px={0} pt={6}>
                  <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
                    <CardHeader>
                      <HStack justify="space-between">
                        <Heading size="md" color="gray.700">
                          API Key
                        </Heading>
                        {isFetchingApiKey && (
                          <Spinner size="sm" color="blue.500" />
                        )}
                      </HStack>
                    </CardHeader>
                    <CardBody>
                <VStack spacing={4} align="stretch">
                  {isFetchingApiKey ? (
                    <Center py={8}>
                      <VStack spacing={4}>
                        <Spinner size="lg" color="blue.500" />
                        <Text color="gray.600">Loading API keys...</Text>
                      </VStack>
                    </Center>
                  ) : (
                    <>
                      {/* Only show "Your API Key" input when there are API keys or when loading */}
                      {(apiKeys.length > 0 || isLoadingApiKeys) && (
                      <FormControl>
                        <FormLabel fontWeight="semibold">Your API Key</FormLabel>
                        <InputGroup>
                          <Input
                            type={showApiKey ? "text" : "password"}
                            value={showApiKey ? (apiKey || "") : maskedApiKey}
                            isReadOnly
                            bg={inputReadOnlyBg}
                            placeholder={apiKey ? undefined : "No API key set"}
                          />
                          <InputRightElement width="8rem">
                            <HStack spacing={1}>
                              <IconButton
                                aria-label={showApiKey ? "Hide API key" : "Show API key"}
                                icon={showApiKey ? <ViewOffIcon /> : <ViewIcon />}
                                onClick={() => setShowApiKey(!showApiKey)}
                                variant="ghost"
                                size="sm"
                                isDisabled={!apiKey}
                              />
                              {apiKey && (
                                <IconButton
                                  aria-label="Copy API key"
                                  icon={<CopyIcon />}
                                  onClick={handleCopyApiKey}
                                  variant="ghost"
                                  size="sm"
                                />
                              )}
                            </HStack>
                          </InputRightElement>
                        </InputGroup>
                        {!apiKey && (
                          <Text fontSize="sm" color="gray.500" mt={2}>
                            You haven&apos;t set an API key yet. Use the &quot;Manage API Key&quot; option in the header to set one.
                          </Text>
                        )}
                      </FormControl>
                      )}
                      
                      {/* Display fetched API keys list */}
                      {apiKeys.length > 0 ? (
                        <Box>
                          <Heading size="sm" mb={4} color="gray.700">
                            Your API Keys ({apiKeys.length})
                          </Heading>
                          <Text fontSize="sm" color="gray.600" mb={3}>
                            Select an API key to use it as your current key
                          </Text>
                          <VStack spacing={2} align="stretch">
                            {apiKeys.map((key) => (
                              <Card 
                                key={key.id} 
                                bg={inputReadOnlyBg} 
                                borderColor={selectedApiKeyId === key.id ? "blue.500" : cardBorder}
                                borderWidth={selectedApiKeyId === key.id ? "2px" : "1px"}
                              >
                                <CardBody p={4}>
                                  <VStack align="stretch" spacing={3}>
                                    <HStack justify="space-between" align="flex-start">
                                      <HStack spacing={3} flex={1}>
                                        <Checkbox
                                          isChecked={selectedApiKeyId === key.id}
                                          onChange={(e) => {
                                            if (e.target.checked) {
                                              // User explicitly selected this key - persist it
                                              setSelectedApiKeyId(key.id);
                                              // If key_value is available, set it as the current API key
                                              if (key.key_value) {
                                                setApiKey(key.key_value);
                                                toast({
                                                  title: "API Key Selected",
                                                  description: `API key "${key.key_name}" has been set as your current key`,
                                                  status: "success",
                                                  duration: 3000,
                                                  isClosable: true,
                                                });
                                              } else {
                                                // Key value not available (only shown once on creation)
                                                // Still persist the selection even without the value
                                                toast({
                                                  title: "API Key Selected",
                                                  description: `API key "${key.key_name}" is now selected. Key value is not available (only shown once on creation).`,
                                                  status: "info",
                                                  duration: 4000,
                                                  isClosable: true,
                                                });
                                              }
                                            } else {
                                              // User explicitly deselected - clear selection
                                              setSelectedApiKeyId(null);
                                            }
                                          }}
                                          colorScheme="blue"
                                          size="lg"
                                        >
                                          <Box>
                                            <Text fontWeight="semibold">{key.key_name}</Text>
                                          </Box>
                                        </Checkbox>
                                      </HStack>
                                      <Badge colorScheme={key.is_active ? "green" : "red"}>
                                        {key.is_active ? "Active" : "Inactive"}
                                      </Badge>
                                    </HStack>
                                    <Text fontSize="sm" color="gray.600">
                                      Created: {new Date(key.created_at).toLocaleString()}
                                    </Text>
                                    {key.expires_at && (
                                      <Text fontSize="sm" color="gray.600">
                                        Expires: {new Date(key.expires_at).toLocaleString()}
                                      </Text>
                                    )}
                                    {key.permissions.length > 0 && (
                                      <HStack flexWrap="wrap" spacing={2}>
                                        <Text fontSize="xs" color="gray.500">Permissions:</Text>
                                        {key.permissions.map((perm) => (
                                          <Badge key={perm} colorScheme="blue" fontSize="xs">
                                            {perm}
                                          </Badge>
                                        ))}
                                      </HStack>
                                    )}
                                    {key.key_value && (
                                      <Alert status="info" borderRadius="md" mt={2}>
                                        <AlertIcon />
                                        <AlertDescription fontSize="xs">
                                          Key value is only shown once. Make sure to save it securely.
                                        </AlertDescription>
                                      </Alert>
                                    )}
                                  </VStack>
                                </CardBody>
                              </Card>
                            ))}
                          </VStack>
                        </Box>
                      ) : !isLoadingApiKeys ? (
                        <Alert status="info" borderRadius="md">
                          <AlertIcon />
                          <AlertDescription>
                            <Text fontWeight="semibold" mb={2}>
                              No API keys found
                            </Text>
                            <Text fontSize="sm">
                              You don&apos;t have any API keys yet. To get an API key, please contact your administrator to add the necessary permissions to your account.
                            </Text>
                          </AlertDescription>
                        </Alert>
                      ) : null}
                    </>
                  )}
                    </VStack>
                  </CardBody>
                </Card>
                </TabPanel>

                {/* Roles Tab - Only visible to ADMIN users */}
                {(user?.roles?.includes('ADMIN') || user?.is_superuser) && (
                  <TabPanel px={0} pt={6}>
                    <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
                      <CardHeader>
                        <Heading size="md" color="gray.700">
                          Role-Based Access Control (RBAC)
                        </Heading>
                      </CardHeader>
                      <CardBody>
                        <VStack spacing={6} align="stretch">
                          {/* Load Roles Button */}
                          <HStack justify="space-between">
                            <Text fontSize="sm" color="gray.600">
                              Manage user roles and permissions
                            </Text>
                            <Button
                              size="sm"
                              colorScheme="blue"
                              onClick={async () => {
                                setIsLoadingRoles(true);
                                try {
                                  const allRoles = await roleService.listRoles();
                                  setRoles(allRoles);
                                  toast({
                                    title: "Roles Loaded",
                                    description: `Loaded ${allRoles.length} roles`,
                                    status: "success",
                                    duration: 2000,
                                    isClosable: true,
                                  });
                                } catch (error) {
                                  toast({
                                    title: "Error",
                                    description: error instanceof Error ? error.message : "Failed to load roles",
                                    status: "error",
                                    duration: 5000,
                                    isClosable: true,
                                  });
                                } finally {
                                  setIsLoadingRoles(false);
                                }
                              }}
                              isLoading={isLoadingRoles}
                              loadingText="Loading..."
                            >
                              Load Roles
                            </Button>
                          </HStack>

                          {/* User Selection */}
                          <Box>
                            <Heading size="sm" mb={4} color="gray.700">
                              Select User
                            </Heading>
                            <FormControl>
                              <FormLabel fontWeight="semibold">User</FormLabel>
                              <Select
                                value={selectedUser?.id || ""}
                                onChange={async (e) => {
                                  const userId = parseInt(e.target.value);
                                  // Find user from fetched users list
                                  const user = users.find(u => u.id === userId);
                                  if (user) {
                                    setSelectedUser({
                                      id: user.id,
                                      email: user.email,
                                      username: user.username || "",
                                    });
                                    setIsLoadingUserRoles(true);
                                    try {
                                      // API: GET /api/v1/auth/roles/user/{user_id}
                                      const userRolesData = await roleService.getUserRoles(user.id);
                                      setSelectedUserRoles(userRolesData.roles);
                                    } catch (error) {
                                      toast({
                                        title: "Error",
                                        description: error instanceof Error ? error.message : "Failed to load user roles",
                                        status: "error",
                                        duration: 5000,
                                        isClosable: true,
                                      });
                                      setSelectedUserRoles([]);
                                    } finally {
                                      setIsLoadingUserRoles(false);
                                    }
                                  } else {
                                    setSelectedUser(null);
                                    setSelectedUserRoles([]);
                                  }
                                }}
                                placeholder={isLoadingUsers ? "Loading users..." : "Select a user"}
                                bg="white"
                                isDisabled={isLoadingUsers}
                              >
                                {users.map((u) => (
                                  <option key={u.id} value={u.id}>
                                    {u.username} ({u.email})
                                  </option>
                                ))}
                              </Select>
                              <Text fontSize="xs" color="gray.500" mt={1}>
                                Using placeholder users - API integration pending
                              </Text>
                            </FormControl>
                          </Box>

                          {/* Current User Roles */}
                          {selectedUser && (
                            <Box>
                              <Heading size="sm" mb={4} color="gray.700">
                                Current Roles for {selectedUser.username}
                              </Heading>
                              {isLoadingUserRoles ? (
                                <Center py={4}>
                                  <Spinner size="md" color="blue.500" />
                                </Center>
                              ) : selectedUserRoles.length > 0 ? (
                                <VStack spacing={2} align="stretch">
                                  {selectedUserRoles.map((roleName) => (
                                    <HStack key={roleName} justify="space-between" p={3} bg={inputReadOnlyBg} borderRadius="md">
                                      <Badge colorScheme="green" fontSize="sm" p={1}>
                                        {roleName}
                                      </Badge>
                                      <Button
                                        size="xs"
                                        colorScheme="red"
                                        variant="outline"
                                        onClick={async () => {
                                          setIsRemovingRole(true);
                                          try {
                                            await roleService.removeRole(selectedUser.id, roleName);
                                            toast({
                                              title: "Success",
                                              description: `Role ${roleName} removed from user ${selectedUser.username}`,
                                              status: "success",
                                              duration: 3000,
                                              isClosable: true,
                                            });
                                            // Refresh user roles
                                            const userRolesData = await roleService.getUserRoles(selectedUser.id);
                                            setSelectedUserRoles(userRolesData.roles);
                                          } catch (error) {
                                            toast({
                                              title: "Error",
                                              description: error instanceof Error ? error.message : "Failed to remove role",
                                              status: "error",
                                              duration: 5000,
                                              isClosable: true,
                                            });
                                          } finally {
                                            setIsRemovingRole(false);
                                          }
                                        }}
                                        isLoading={isRemovingRole}
                                        loadingText="Removing..."
                                      >
                                        Remove
                                      </Button>
                                    </HStack>
                                  ))}
                                </VStack>
                              ) : (
                                <Alert status="info" borderRadius="md">
                                  <AlertIcon />
                                  <AlertDescription>
                                    This user has no roles assigned.
                                  </AlertDescription>
                                </Alert>
                              )}
                            </Box>
                          )}

                          {/* Assign Role Section */}
                          {selectedUser && roles.length > 0 && (
                            <Box>
                              <Heading size="sm" mb={4} color="gray.700">
                                Assign Role to {selectedUser.username}
                              </Heading>
                              <VStack spacing={4} align="stretch">
                                <FormControl>
                                  <FormLabel fontWeight="semibold">Select Role</FormLabel>
                                  <Select
                                    value={selectedRole}
                                    onChange={(e) => setSelectedRole(e.target.value)}
                                    placeholder="Select a role to assign"
                                    bg="white"
                                  >
                                    {roles
                                      .filter((role) => !selectedUserRoles.includes(role.name))
                                      .map((role) => (
                                        <option key={role.id} value={role.name}>
                                          {role.name} - {role.description || "No description"}
                                        </option>
                                      ))}
                                  </Select>
                                  {selectedUserRoles.length > 0 && (
                                    <Text fontSize="xs" color="gray.500" mt={1}>
                                      Only showing roles not already assigned to this user
                                    </Text>
                                  )}
                                </FormControl>
                                <Button
                                  colorScheme="green"
                                  onClick={async () => {
                                    if (!selectedRole) {
                                      toast({
                                        title: "Validation Error",
                                        description: "Please select a role",
                                        status: "error",
                                        duration: 3000,
                                        isClosable: true,
                                      });
                                      return;
                                    }
                                    setIsAssigningRole(true);
                                    try {
                                      await roleService.assignRole(selectedUser.id, selectedRole);
                                      toast({
                                        title: "Success",
                                        description: `Role ${selectedRole} assigned to user ${selectedUser.username}`,
                                        status: "success",
                                        duration: 3000,
                                        isClosable: true,
                                      });
                                      // Refresh user roles
                                      const userRolesData = await roleService.getUserRoles(selectedUser.id);
                                      setSelectedUserRoles(userRolesData.roles);
                                      setSelectedRole("");
                                    } catch (error) {
                                      toast({
                                        title: "Error",
                                        description: error instanceof Error ? error.message : "Failed to assign role",
                                        status: "error",
                                        duration: 5000,
                                        isClosable: true,
                                      });
                                    } finally {
                                      setIsAssigningRole(false);
                                    }
                                  }}
                                  isLoading={isAssigningRole}
                                  loadingText="Assigning..."
                                  isDisabled={!selectedRole}
                                >
                                  Assign Role
                                </Button>
                              </VStack>
                            </Box>
                          )}

                          {/* Available Roles List */}
                          {roles.length > 0 && (
                            <Box>
                              <Heading size="sm" mb={4} color="gray.700">
                                Available Roles
                              </Heading>
                              <TableContainer>
                                <Table variant="simple" size="sm">
                                  <Thead>
                                    <Tr>
                                      <Th>Role Name</Th>
                                      <Th>Description</Th>
                                    </Tr>
                                  </Thead>
                                  <Tbody>
                                    {roles.map((role) => (
                                      <Tr key={role.id}>
                                        <Td>
                                          <Badge colorScheme="blue" fontSize="sm" p={1}>
                                            {role.name}
                                          </Badge>
                                        </Td>
                                        <Td>
                                          <Text fontSize="sm" color="gray.600">
                                            {role.description || "No description"}
                                          </Text>
                                        </Td>
                                      </Tr>
                                    ))}
                                  </Tbody>
                                </Table>
                              </TableContainer>
                            </Box>
                          )}

                          <Alert status="info" borderRadius="md">
                            <AlertIcon />
                            <AlertDescription>
                              Only administrators can manage roles. Select a user to view and manage their roles.
                            </AlertDescription>
                          </Alert>
                        </VStack>
                      </CardBody>
                    </Card>
                  </TabPanel>
                )}

             
                {/* Permissions Tab - Only visible to ADMIN users */}
                {(user?.roles?.includes('ADMIN') || user?.is_superuser) && (
                  <TabPanel px={0} pt={6}>
                    <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
                      <CardHeader>
                        <Heading size="md" color="gray.700">
                          Permissions Management
                        </Heading>
                      </CardHeader>
                      <CardBody>
                        <VStack spacing={6} align="stretch">
                          {/* Load Permissions Button */}
                          <HStack justify="space-between">
                            <Text fontSize="sm" color="gray.600">
                              Assign permissions to users
                            </Text>
                            <Button
                              size="sm"
                              colorScheme="purple"
                              onClick={async () => {
                                setIsLoadingPermissions(true);
                                try {
                                  const allPermissions = await authService.getAllPermissions();
                                  setPermissions(allPermissions);
                                  toast({
                                    title: "Permissions Loaded",
                                    description: `Loaded ${allPermissions.length} permissions`,
                                    status: "success",
                                    duration: 2000,
                                    isClosable: true,
                                  });
                                } catch (error) {
                                  toast({
                                    title: "Error",
                                    description: error instanceof Error ? error.message : "Failed to load permissions",
                                    status: "error",
                                    duration: 5000,
                                    isClosable: true,
                                  });
                                } finally {
                                  setIsLoadingPermissions(false);
                                }
                              }}
                              isLoading={isLoadingPermissions}
                              loadingText="Loading..."
                            >
                              Load Permissions
                            </Button>
                          </HStack>

                          {/* User Selection */}
                          <Box>
                            <Heading size="sm" mb={4} color="gray.700">
                              Select User
                            </Heading>
                            <FormControl>
                              <FormLabel fontWeight="semibold">User</FormLabel>
                              <Select
                                value={selectedUserForPermissions?.id || ""}
                                onChange={async (e) => {
                                  const userId = parseInt(e.target.value);
                                  const user = users.find((u) => u.id === userId);
                                  if (user) {
                                    setSelectedUserForPermissions({
                                      id: user.id,
                                      email: user.email,
                                      username: user.username || "",
                                    });
                                    // TODO: Load user's current permissions from API
                                    setSelectedUserPermissions([]);
                                  } else {
                                    setSelectedUserForPermissions(null);
                                    setSelectedUserPermissions([]);
                                  }
                                }}
                                placeholder={isLoadingUsers ? "Loading users..." : "Select a user"}
                                bg="white"
                                isDisabled={isLoadingUsers}
                              >
                                {users.map((u) => (
                                  <option key={u.id} value={u.id}>
                                    {u.username} ({u.email})
                                  </option>
                                ))}
                              </Select>
                            </FormControl>
                          </Box>

                          {/* Current User Permissions */}
                          {selectedUserForPermissions && (
                            <Box>
                              <Heading size="sm" mb={4} color="gray.700">
                                Current Permissions for {selectedUserForPermissions.username}
                              </Heading>
                              {selectedUserPermissions.length > 0 ? (
                                <VStack spacing={2} align="stretch">
                                  {selectedUserPermissions.map((perm) => (
                                    <HStack key={perm} justify="space-between" p={3} bg={inputReadOnlyBg} borderRadius="md">
                                      <Badge colorScheme="purple" fontSize="sm" p={1}>
                                        {perm}
                                      </Badge>
                                      <Button
                                        size="xs"
                                        colorScheme="red"
                                        variant="outline"
                                        onClick={async () => {
                                          // TODO: Implement remove permission API call
                                          toast({
                                            title: "Info",
                                            description: "Remove permission functionality will be implemented",
                                            status: "info",
                                            duration: 3000,
                                            isClosable: true,
                                          });
                                        }}
                                      >
                                        Remove
                                      </Button>
                                    </HStack>
                                  ))}
                                </VStack>
                              ) : (
                                <Alert status="info" borderRadius="md">
                                  <AlertIcon />
                                  <AlertDescription>
                                    This user has no direct permissions assigned (permissions come from roles).
                                  </AlertDescription>
                                </Alert>
                              )}
                            </Box>
                          )}

                          {/* Create API Key for User Section */}
                          {selectedUserForPermissions && permissions.length > 0 && (
                            <Box>
                              <Heading size="sm" mb={4} color="gray.700">
                                Create API Key for {selectedUserForPermissions.username}
                              </Heading>
                              <VStack spacing={4} align="stretch">
                                <FormControl>
                                  <FormLabel fontWeight="semibold">Key Name</FormLabel>
                                  <Input
                                    value={apiKeyForUser.key_name}
                                    onChange={(e) => setApiKeyForUser({ ...apiKeyForUser, key_name: e.target.value })}
                                    placeholder="Enter a name for this API key"
                                    bg="white"
                                  />
                                </FormControl>

                                <FormControl>
                                  <FormLabel fontWeight="semibold">Permissions</FormLabel>
                                  <Text fontSize="sm" color="gray.600" mb={3}>
                                    Select permissions to find matching API key
                                  </Text>
                                  {permissions.length > 0 ? (
                                    <Box
                                      borderWidth="1px"
                                      borderRadius="md"
                                      p={4}
                                      bg="white"
                                      maxH="300px"
                                      overflowY="auto"
                                    >
                                      <CheckboxGroup
                                        value={selectedPermissionsForUser}
                                        onChange={(values) => {
                                          setSelectedPermissionsForUser(values as string[]);
                                        }}
                                      >
                                        {/* Select All / Deselect All Button */}
                                        <Box mb={3} pb={3} borderBottomWidth="1px">
                                          <HStack justify="space-between" align="center">
                                            <Checkbox
                                              isChecked={selectedPermissionsForUser.length === permissions.length && permissions.length > 0}
                                              onChange={(e) => {
                                                if (e.target.checked) {
                                                  setSelectedPermissionsForUser([...permissions]);
                                                } else {
                                                  setSelectedPermissionsForUser([]);
                                                }
                                              }}
                                              colorScheme="purple"
                                            >
                                              <Text fontSize="sm" fontWeight="semibold">
                                                Select All
                                              </Text>
                                            </Checkbox>
                                            <Text fontSize="xs" color="gray.500">
                                              {selectedPermissionsForUser.length}/{permissions.length} selected
                                            </Text>
                                          </HStack>
                                        </Box>
                                        
                                        <SimpleGrid columns={2} spacing={3}>
                                          {permissions.map((perm) => (
                                            <Checkbox key={perm} value={perm} colorScheme="purple">
                                              <Text fontSize="sm">{perm}</Text>
                                            </Checkbox>
                                          ))}
                                        </SimpleGrid>
                                      </CheckboxGroup>
                                    </Box>
                                  ) : (
                                    <Alert status="info" borderRadius="md">
                                      <AlertIcon />
                                      <AlertDescription>
                                        Click &quot;Load Permissions&quot; to view available permissions
                                      </AlertDescription>
                                    </Alert>
                                  )}
                                  {selectedPermissionsForUser.length > 0 && (
                                    <Box mt={3}>
                                      <Text fontSize="sm" fontWeight="semibold" mb={2} color="gray.700">
                                        Selected Permissions ({selectedPermissionsForUser.length}):
                                      </Text>
                                      <HStack flexWrap="wrap" spacing={2}>
                                        {selectedPermissionsForUser.map((perm) => (
                                          <Badge key={perm} colorScheme="purple" fontSize="sm" p={1}>
                                            {perm}
                                          </Badge>
                                        ))}
                                      </HStack>
                                    </Box>
                                  )}
                                </FormControl>

                                <FormControl>
                                  <FormLabel fontWeight="semibold">Expiry (Days)</FormLabel>
                                  <Input
                                    type="number"
                                    value={apiKeyForUser.expires_days}
                                    onChange={(e) => setApiKeyForUser({ ...apiKeyForUser, expires_days: parseInt(e.target.value) || 30 })}
                                    min={1}
                                    max={365}
                                    bg="white"
                                  />
                                  <Text fontSize="xs" color="gray.500" mt={1}>
                                    API key will expire after {apiKeyForUser.expires_days} day(s)
                                  </Text>
                                </FormControl>

                                <Button
                                  colorScheme="purple"
                                  onClick={async () => {
                                    if (!apiKeyForUser.key_name.trim()) {
                                      toast({
                                        title: "Validation Error",
                                        description: "Please enter a key name",
                                        status: "error",
                                        duration: 3000,
                                        isClosable: true,
                                      });
                                      return;
                                    }
                                    if (selectedPermissionsForUser.length === 0) {
                                      toast({
                                        title: "Validation Error",
                                        description: "Please select at least one permission",
                                        status: "error",
                                        duration: 3000,
                                        isClosable: true,
                                      });
                                      return;
                                    }
                                    setIsCreatingApiKeyForUser(true);
                                    try {
                                      // Create API key payload with userId (camelCase as per API spec)
                                      const payload = {
                                        key_name: apiKeyForUser.key_name,
                                        permissions: selectedPermissionsForUser,
                                        expires_days: apiKeyForUser.expires_days,
                                        userId: selectedUserForPermissions.id,
                                      };
                                      
                                      // Send the payload directly with userId
                                      const createdKey = await authService.createApiKeyForUser({
                                        key_name: payload.key_name,
                                        permissions: payload.permissions,
                                        expires_days: payload.expires_days,
                                        user_id: payload.userId, // TypeScript interface uses user_id, but payload will have userId
                                      });
                                      
                                      // If the created key has a key_value, set it in the API key box
                                      if (createdKey.key_value) {
                                        setApiKey(createdKey.key_value);
                                        // Set the newly created key as selected
                                        setSelectedApiKeyId(createdKey.id);
                                      }
                                      
                                      // Refresh API keys list to include the new key
                                      try {
                                        const updatedApiKeys = await authService.listApiKeys();
                                        setApiKeys(updatedApiKeys);
                                        // Update selected key ID if we have it
                                        if (createdKey.id) {
                                          setSelectedApiKeyId(createdKey.id);
                                        }
                                      } catch (error) {
                                        console.error("Failed to refresh API keys list:", error);
                                      }
                                      
                                      toast({
                                        title: "API Key Created",
                                        description: `API key "${createdKey.key_name}" created successfully for ${selectedUserForPermissions.username}.`,
                                        status: "success",
                                        duration: 5000,
                                        isClosable: true,
                                      });
                                      
                                      // Reset form
                                      setApiKeyForUser({ key_name: "", permissions: [], expires_days: 30 });
                                      setSelectedPermissionsForUser([]);
                                    } catch (error) {
                                      toast({
                                        title: "Error",
                                        description: error instanceof Error ? error.message : "Failed to create API key",
                                        status: "error",
                                        duration: 5000,
                                        isClosable: true,
                                      });
                                    } finally {
                                      setIsCreatingApiKeyForUser(false);
                                    }
                                  }}
                                  isLoading={isCreatingApiKeyForUser}
                                  loadingText="Creating..."
                                >
                                  Add Permission (Create API Key)
                                </Button>
                              </VStack>
                            </Box>
                          )}

                          {permissions.length === 0 && !isLoadingPermissions && (
                            <Alert status="info" borderRadius="md">
                              <AlertIcon />
                              <AlertDescription>
                                Click &quot;Load Permissions&quot; to view all available permissions in the system.
                              </AlertDescription>
                            </Alert>
                          )}

                          <Alert status="info" borderRadius="md">
                            <AlertIcon />
                            <AlertDescription>
                              Permissions are typically assigned through roles. Direct permission assignment may require backend support.
                            </AlertDescription>
                          </Alert>
                        </VStack>
                      </CardBody>
                    </Card>
                  </TabPanel>
                )}
              </TabPanels>
            </Tabs>
          </Card>
        </Box>
      </ContentLayout>
    </>
  );
};

export default ProfilePage;
