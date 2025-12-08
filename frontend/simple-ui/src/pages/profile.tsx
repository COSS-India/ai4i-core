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
} from "@chakra-ui/react";
import { ViewIcon, ViewOffIcon, CopyIcon } from "@chakra-ui/icons";
import { FiEdit2, FiCheck, FiX } from "react-icons/fi";
import Head from "next/head";
import React, { useState, useEffect } from "react";
import { useRouter } from "next/router";
import ContentLayout from "../components/common/ContentLayout";
import { useAuth } from "../hooks/useAuth";
import { useApiKey } from "../hooks/useApiKey";
import { User, UserUpdateRequest } from "../types/auth";
import roleService, { Role, UserRole } from "../services/roleService";

const ProfilePage: React.FC = () => {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading, updateUser } = useAuth();
  const { apiKey, getApiKey } = useApiKey();
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
  const [selectedUser, setSelectedUser] = useState<{ id: number; email: string; username: string } | null>(null);
  const [selectedUserRoles, setSelectedUserRoles] = useState<string[]>([]);
  const [selectedRole, setSelectedRole] = useState<string>("");
  const [isLoadingRoles, setIsLoadingRoles] = useState(false);
  const [isLoadingUserRoles, setIsLoadingUserRoles] = useState(false);
  const [isAssigningRole, setIsAssigningRole] = useState(false);
  const [isRemovingRole, setIsRemovingRole] = useState(false);
  
  // Placeholder users list - TODO: Replace with API call to GET /api/v1/auth/users/list (when available)
  // For now, using dummy data to handle errors and test the UI
  const placeholderUsers = [
    { id: 1, email: "admin@ai4i.com", username: "admin" },
    { id: 2, email: "user@example.com", username: "user1" },
    { id: 3, email: "moderator@example.com", username: "moderator1" },
    { id: 4, email: "guest@example.com", username: "guest1" },
    { id: 5, email: "test@example.com", username: "testuser" },
  ];

  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");

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
            <Tabs colorScheme="blue" variant="enclosed">
              <TabList>
                <Tab fontWeight="semibold">User Details</Tab>
                <Tab fontWeight="semibold">Organization</Tab>
                {/* <Tab fontWeight="semibold">API Key</Tab> */}
                {(user?.roles?.includes('ADMIN') || user?.is_superuser) && (
                  <Tab fontWeight="semibold">Roles</Tab>
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
                      bg={isEditingUser ? "white" : useColorModeValue("gray.50", "gray.700")}
                      placeholder="Enter your full name"
                    />
                  </FormControl>

                  <FormControl>
                    <FormLabel fontWeight="semibold">Username</FormLabel>
                    <Input
                      value={user.username || "N/A"}
                      isReadOnly
                      bg={useColorModeValue("gray.50", "gray.700")}
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
                      bg={useColorModeValue("gray.50", "gray.700")}
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
                      bg={isEditingUser ? "white" : useColorModeValue("gray.50", "gray.700")}
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
                          bg={useColorModeValue("gray.50", "gray.700")}
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
                          bg={useColorModeValue("gray.50", "gray.700")}
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
                        bg={useColorModeValue("gray.50", "gray.700")}
                      />
                    </FormControl>

                    <FormControl flex={1}>
                      <FormLabel fontWeight="semibold">Verified</FormLabel>
                      <Input
                        value={user.is_verified ? "Yes" : "No"}
                        isReadOnly
                        bg={useColorModeValue("gray.50", "gray.700")}
                      />
                    </FormControl>
                  </HStack>

                  {user.created_at && (
                    <FormControl>
                      <FormLabel fontWeight="semibold">Member Since</FormLabel>
                      <Input
                        value={new Date(user.created_at).toLocaleDateString()}
                        isReadOnly
                        bg={useColorModeValue("gray.50", "gray.700")}
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
                      bg={useColorModeValue("gray.50", "gray.700")}
                    />
                  </FormControl>

                  <FormControl>
                    <FormLabel fontWeight="semibold">Organization ID</FormLabel>
                    <Input
                      value="Not Available"
                      isReadOnly
                      bg={useColorModeValue("gray.50", "gray.700")}
                    />
                  </FormControl>

                  <FormControl>
                    <FormLabel fontWeight="semibold">Role</FormLabel>
                    <Input
                      value="Not Available"
                      isReadOnly
                      bg={useColorModeValue("gray.50", "gray.700")}
                    />
                  </FormControl>
                    </VStack>
                  </CardBody>
                </Card>
                </TabPanel>

                {/* API Key Tab */}
                {/* <TabPanel px={0} pt={6}>
                  <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
                    <CardHeader>
                      <Heading size="md" color="gray.700">
                        API Key
                      </Heading>
                    </CardHeader>
                    <CardBody>
                <VStack spacing={4} align="stretch">
                  <FormControl>
                    <FormLabel fontWeight="semibold">Your API Key</FormLabel>
                    <InputGroup>
                      <Input
                        type={showApiKey ? "text" : "password"}
                        value={showApiKey ? (apiKey || "") : maskedApiKey}
                        isReadOnly
                        bg={useColorModeValue("gray.50", "gray.700")}
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
                    </VStack>
                  </CardBody>
                </Card>
                </TabPanel> */}

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
                                  // Find user from placeholder list (will be replaced with API call later)
                                  const user = placeholderUsers.find(u => u.id === userId);
                                  if (user) {
                                    setSelectedUser(user);
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
                                placeholder="Select a user"
                                bg="white"
                              >
                                {placeholderUsers.map((u) => (
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
                                    <HStack key={roleName} justify="space-between" p={3} bg={useColorModeValue("gray.50", "gray.700")} borderRadius="md">
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
              </TabPanels>
            </Tabs>
          </Card>
        </Box>
      </ContentLayout>
    </>
  );
};

export default ProfilePage;
