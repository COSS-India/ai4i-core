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
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalFooter,
  ModalBody,
  ModalCloseButton,
  AlertDialog,
  AlertDialogBody,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogContent,
  AlertDialogOverlay,
} from "@chakra-ui/react";
import { ViewIcon, ViewOffIcon, CopyIcon } from "@chakra-ui/icons";
import { FiEdit2, FiCheck, FiX } from "react-icons/fi";
import Head from "next/head";
import React, { useState, useEffect, useRef } from "react";
import { useRouter } from "next/router";
import ContentLayout from "../components/common/ContentLayout";
import { useAuth } from "../hooks/useAuth";
import { useApiKey } from "../hooks/useApiKey";
import { User, UserUpdateRequest, Permission, APIKeyResponse, AdminAPIKeyWithUserResponse, APIKeyUpdate } from "../types/auth";
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

  // API Key Management state (for Admin/Moderator)
  const [allApiKeys, setAllApiKeys] = useState<AdminAPIKeyWithUserResponse[]>([]);
  const [isLoadingAllApiKeys, setIsLoadingAllApiKeys] = useState(false);
  const [filterUser, setFilterUser] = useState<string>("all"); // "all" or user ID
  const [filterPermission, setFilterPermission] = useState<string>("all"); // "all" or permission name
  const [filterActive, setFilterActive] = useState<string>("all"); // "all", "active", "inactive"
  const [selectedKeyForUpdate, setSelectedKeyForUpdate] = useState<AdminAPIKeyWithUserResponse | null>(null);
  const [isUpdateModalOpen, setIsUpdateModalOpen] = useState(false);
  const [isRevokeModalOpen, setIsRevokeModalOpen] = useState(false);
  const [keyToRevoke, setKeyToRevoke] = useState<AdminAPIKeyWithUserResponse | null>(null);
  const [isRevoking, setIsRevoking] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [updateFormData, setUpdateFormData] = useState<APIKeyUpdate>({
    key_name: "",
    permissions: [],
    is_active: true,
  });
  const cancelRef = useRef<HTMLButtonElement>(null);
  const [selectedKeyForView, setSelectedKeyForView] = useState<AdminAPIKeyWithUserResponse | null>(null);
  const [isViewModalOpen, setIsViewModalOpen] = useState(false);
  
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

  // API Key Management handlers (Admin/Moderator)
  const handleFetchAllApiKeys = async () => {
    setIsLoadingAllApiKeys(true);
    try {
      const allKeys = await authService.listAllApiKeys();
      setAllApiKeys(allKeys);
      
      // Also ensure users and permissions are loaded for filters
      if (users.length === 0 && !isLoadingUsers) {
        try {
          const usersList = await authService.getAllUsers();
          setUsers(usersList);
        } catch (err) {
          console.error("Failed to fetch users for filter:", err);
        }
      }
      
      if (permissions.length === 0 && !isLoadingPermissions) {
        try {
          const permsList = await authService.getAllPermissions();
          setPermissions(permsList);
        } catch (err) {
          console.error("Failed to fetch permissions for filter:", err);
        }
      }
      
      toast({
        title: "API Keys Loaded",
        description: `Loaded ${allKeys.length} API key(s)`,
        status: "success",
        duration: 2000,
        isClosable: true,
      });
    } catch (error) {
      console.error("Failed to fetch all API keys:", error);
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to load API keys",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsLoadingAllApiKeys(false);
    }
  };

  const handleOpenUpdateModal = (key: AdminAPIKeyWithUserResponse) => {
    setSelectedKeyForUpdate(key);
    setUpdateFormData({
      key_name: key.key_name,
      permissions: [...key.permissions],
      is_active: key.is_active,
    });
    setIsUpdateModalOpen(true);
  };

  const handleCloseUpdateModal = () => {
    setIsUpdateModalOpen(false);
    setSelectedKeyForUpdate(null);
    setUpdateFormData({
      key_name: "",
      permissions: [],
      is_active: true,
    });
  };

  const handleUpdateApiKey = async () => {
    if (!selectedKeyForUpdate) return;

    setIsUpdating(true);
    try {
      await authService.updateApiKey(selectedKeyForUpdate.id, updateFormData);
      toast({
        title: "API Key Updated",
        description: "API key has been updated successfully",
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      handleCloseUpdateModal();
      // Refresh the list
      await handleFetchAllApiKeys();
    } catch (error) {
      toast({
        title: "Update Failed",
        description: error instanceof Error ? error.message : "Failed to update API key",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsUpdating(false);
    }
  };

  const handleOpenRevokeModal = (key: AdminAPIKeyWithUserResponse) => {
    setKeyToRevoke(key);
    setIsRevokeModalOpen(true);
  };

  const handleCloseRevokeModal = () => {
    setIsRevokeModalOpen(false);
    setKeyToRevoke(null);
  };

  const handleOpenViewModal = (key: AdminAPIKeyWithUserResponse) => {
    setSelectedKeyForView(key);
    setIsViewModalOpen(true);
  };

  const handleCloseViewModal = () => {
    setIsViewModalOpen(false);
    setSelectedKeyForView(null);
  };

  const handleResetFilters = () => {
    setFilterUser("all");
    setFilterPermission("all");
    setFilterActive("all");
  };

  const handleRevokeApiKey = async () => {
    if (!keyToRevoke) return;

    setIsRevoking(true);
    try {
      await authService.revokeApiKey(keyToRevoke.id);
      toast({
        title: "API Key Revoked",
        description: "API key has been revoked successfully",
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      handleCloseRevokeModal();
      // Refresh the list
      await handleFetchAllApiKeys();
    } catch (error) {
      toast({
        title: "Revoke Failed",
        description: error instanceof Error ? error.message : "Failed to revoke API key",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsRevoking(false);
    }
  };

  // Filter API keys based on user, permission, and active status
  const filteredApiKeys = allApiKeys
    .filter((key) => {
      if (filterUser !== "all" && key.user_id.toString() !== filterUser) {
        return false;
      }
      if (filterPermission !== "all" && !key.permissions.includes(filterPermission)) {
        return false;
      }
      if (filterActive === "active" && !key.is_active) {
        return false;
      }
      if (filterActive === "inactive" && key.is_active) {
        return false;
      }
      return true;
    })
    .sort((a, b) => {
      const dateA = new Date(a.created_at).getTime();
      const dateB = new Date(b.created_at).getTime();
      return dateB - dateA; // Descending order (newest first)
    });

  // Get unique permissions from all API keys for the filter dropdown
  const allUniquePermissions = React.useMemo(() => {
    const perms = new Set<string>();
    allApiKeys.forEach(key => {
      key.permissions.forEach(perm => perms.add(perm));
    });
    return Array.from(perms).sort();
  }, [allApiKeys]);

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
        <Box 
          maxW={(user?.roles?.includes('ADMIN') || user?.roles?.includes('MODERATOR') || user?.is_superuser) ? "7xl" : "4xl"} 
          mx="auto" 
          py={8} 
          px={4}
        >
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
                // If API Key Management tab is clicked, fetch all API keys
                const isAdmin = user?.roles?.includes('ADMIN') || user?.is_superuser;
                const isModerator = user?.roles?.includes('MODERATOR');
                // Calculate tab index: User Details(0), Organization(1), API Key(2), Roles(3 if admin), Create API Key(4 if admin), API Key Management(5 if admin, 3 if moderator only)
                const apiKeyManagementTabIndex = isAdmin ? 5 : (isModerator ? 3 : -1);
                if (index === apiKeyManagementTabIndex) {
                  console.log('Profile: API Key Management tab clicked, fetching all API keys');
                  handleFetchAllApiKeys();
                  // Also ensure permissions are loaded for the filter dropdown
                  if (permissions.length === 0 && !isLoadingPermissions) {
                    authService.getAllPermissions().then(setPermissions).catch(console.error);
                  }
                }
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
                    <Tab fontWeight="semibold">Create API Key</Tab>
                  </>
                )}
                {(user?.roles?.includes('ADMIN') || user?.roles?.includes('MODERATOR') || user?.is_superuser) && (
                  <Tab fontWeight="semibold">API Key Management</Tab>
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
                            {[...apiKeys].sort((a, b) => {
                              const dateA = new Date(a.created_at).getTime();
                              const dateB = new Date(b.created_at).getTime();
                              return dateB - dateA; // Descending order (newest first)
                            }).map((key) => (
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

                {/* Roles Tab - Visible to ADMIN (can add/remove) and MODERATOR (view only) */}
                {(user?.roles?.includes('ADMIN') || user?.roles?.includes('MODERATOR') || user?.is_superuser) && (
                  <TabPanel px={0} pt={6}>
                    <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
                      <CardHeader>
                        <HStack justify="space-between">
                          <Heading size="md" color="gray.700">
                            Role-Based Access Control (RBAC)
                          </Heading>
                          {(user?.roles?.includes('MODERATOR') && !user?.roles?.includes('ADMIN') && !user?.is_superuser) && (
                            <Badge colorScheme="orange" fontSize="sm" p={2}>
                              View Only
                            </Badge>
                          )}
                        </HStack>
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
                                        isDisabled={user?.roles?.includes('MODERATOR') && !user?.roles?.includes('ADMIN') && !user?.is_superuser}
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

                          {/* Assign Role Section - Only visible to ADMIN */}
                          {selectedUser && roles.length > 0 && (user?.roles?.includes('ADMIN') || user?.is_superuser) && (
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
                                  isDisabled={!selectedRole || (user?.roles?.includes('MODERATOR') && !user?.roles?.includes('ADMIN') && !user?.is_superuser)}
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

                {/* API Key Management Tab - Visible to ADMIN and MODERATOR */}
                {(user?.roles?.includes('ADMIN') || user?.roles?.includes('MODERATOR') || user?.is_superuser) && (
                  <TabPanel px={0} pt={6}>
                    <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
                      <CardHeader>
                        <HStack justify="space-between">
                          <Heading size="md" color="gray.700">
                            API Key Management
                          </Heading>
                          <Button
                            size="sm"
                            colorScheme="blue"
                            onClick={handleFetchAllApiKeys}
                            isLoading={isLoadingAllApiKeys}
                            loadingText="Loading..."
                          >
                            Refresh
                          </Button>
                        </HStack>
                      </CardHeader>
                      <CardBody>
                        <VStack spacing={6} align="stretch">
                          {/* Filters */}
                          <Box>
                            <HStack justify="space-between" mb={4}>
                              <Heading size="sm" color="gray.700">Filters</Heading>
                              <Button
                                size="sm"
                                variant="outline"
                                colorScheme="gray"
                                onClick={handleResetFilters}
                                isDisabled={filterUser === "all" && filterPermission === "all" && filterActive === "all"}
                              >
                                Reset Filters
                              </Button>
                            </HStack>
                            <SimpleGrid columns={{ base: 1, md: 3 }} spacing={4}>
                              <FormControl>
                                <FormLabel fontWeight="semibold">Filter by User</FormLabel>
                                <Select
                                  value={filterUser}
                                  onChange={(e) => setFilterUser(e.target.value)}
                                  bg="white"
                                  placeholder="All Users"
                                >
                                  <option value="all">All Users</option>
                                  {users.map((user) => (
                                    <option key={user.id} value={user.id.toString()}>
                                      {user.email} ({user.username})
                                    </option>
                                  ))}
                                </Select>
                              </FormControl>
                              <FormControl>
                                <FormLabel fontWeight="semibold">Filter by Permission</FormLabel>
                                <Select
                                  value={filterPermission}
                                  onChange={(e) => setFilterPermission(e.target.value)}
                                  bg="white"
                                  placeholder="All Permissions"
                                >
                                  <option value="all">All Permissions</option>
                                  {allUniquePermissions.length > 0 ? (
                                    allUniquePermissions.map((perm) => (
                                      <option key={perm} value={perm}>
                                        {perm}
                                      </option>
                                    ))
                                  ) : permissions.length > 0 ? (
                                    permissions.map((perm) => (
                                      <option key={perm} value={perm}>
                                        {perm}
                                      </option>
                                    ))
                                  ) : null}
                                </Select>
                              </FormControl>
                              <FormControl>
                                <FormLabel fontWeight="semibold">Status</FormLabel>
                                <Select
                                  value={filterActive}
                                  onChange={(e) => setFilterActive(e.target.value)}
                                  bg="white"
                                >
                                  <option value="all">All</option>
                                  <option value="active">Active</option>
                                  <option value="inactive">Inactive</option>
                                </Select>
                              </FormControl>
                            </SimpleGrid>
                          </Box>

                          {/* API Keys Table */}
                          {isLoadingAllApiKeys ? (
                            <Center py={8}>
                              <VStack spacing={4}>
                                <Spinner size="lg" color="blue.500" />
                                <Text color="gray.600">Loading API keys...</Text>
                              </VStack>
                            </Center>
                          ) : filteredApiKeys.length > 0 ? (
                            <TableContainer>
                              <Table variant="simple">
                                <Thead>
                                  <Tr>
                                    <Th>Key Name</Th>
                                    <Th>User</Th>
                                    <Th>Permissions</Th>
                                    <Th>Status</Th>
                                    <Th>Created</Th>
                                    <Th>Expires</Th>
                                    <Th>Actions</Th>
                                  </Tr>
                                </Thead>
                                <Tbody>
                                  {filteredApiKeys.map((key) => (
                                    <Tr 
                                      key={key.id}
                                      onClick={() => handleOpenViewModal(key)}
                                      cursor="pointer"
                                      _hover={{ bg: "gray.50" }}
                                    >
                                      <Td fontWeight="semibold">{key.key_name}</Td>
                                      <Td>
                                        <VStack align="start" spacing={0}>
                                          <Text fontSize="sm">{key.user_email}</Text>
                                          <Text fontSize="xs" color="gray.500">{key.username}</Text>
                                        </VStack>
                                      </Td>
                                      <Td>
                                        <HStack flexWrap="wrap" spacing={1}>
                                          {key.permissions.slice(0, 3).map((perm) => (
                                            <Badge key={perm} colorScheme="blue" fontSize="xs">
                                              {perm}
                                            </Badge>
                                          ))}
                                          {key.permissions.length > 3 && (
                                            <Badge colorScheme="gray" fontSize="xs">
                                              +{key.permissions.length - 3}
                                            </Badge>
                                          )}
                                        </HStack>
                                      </Td>
                                      <Td>
                                        <Badge colorScheme={key.is_active ? "green" : "red"}>
                                          {key.is_active ? "Active" : "Inactive"}
                                        </Badge>
                                      </Td>
                                      <Td fontSize="sm">
                                        {new Date(key.created_at).toLocaleDateString()}
                                      </Td>
                                      <Td fontSize="sm">
                                        {key.expires_at ? new Date(key.expires_at).toLocaleDateString() : "Never"}
                                      </Td>
                                      <Td>
                                        <HStack spacing={2}>
                                          <Button
                                            size="xs"
                                            colorScheme="blue"
                                            variant="outline"
                                            onClick={(e) => {
                                              e.stopPropagation();
                                              handleOpenViewModal(key);
                                            }}
                                          >
                                            View
                                          </Button>
                                          <Button
                                            size="xs"
                                            colorScheme="green"
                                            onClick={(e) => {
                                              e.stopPropagation();
                                              handleOpenUpdateModal(key);
                                            }}
                                          >
                                            Update
                                          </Button>
                                          <Button
                                            size="xs"
                                            colorScheme="red"
                                            variant="outline"
                                            onClick={(e) => {
                                              e.stopPropagation();
                                              handleOpenRevokeModal(key);
                                            }}
                                            isDisabled={!key.is_active}
                                          >
                                            Revoke
                                          </Button>
                                        </HStack>
                                      </Td>
                                    </Tr>
                                  ))}
                                </Tbody>
                              </Table>
                            </TableContainer>
                          ) : (
                            <Alert status="info" borderRadius="md">
                              <AlertIcon />
                              <AlertDescription>
                                {allApiKeys.length === 0
                                  ? "No API keys found. Click 'Refresh' to load API keys."
                                  : "No API keys match the current filters."}
                              </AlertDescription>
                            </Alert>
                          )}
                        </VStack>
                      </CardBody>
                    </Card>
                  </TabPanel>
                )}
              </TabPanels>
            </Tabs>
          </Card>
        </Box>

        {/* View API Key Modal */}
        <Modal isOpen={isViewModalOpen} onClose={handleCloseViewModal} size="2xl" isCentered>
          <ModalOverlay />
          <ModalContent maxW="900px" maxH="600px">
            <ModalHeader>API Key Details</ModalHeader>
            <ModalCloseButton />
            <ModalBody overflowY="auto">
              {selectedKeyForView && (
                <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                  <Box>
                    <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                      Key Name
                    </Text>
                    <Text fontSize="md">{selectedKeyForView.key_name}</Text>
                  </Box>

                  <Box>
                    <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                      User
                    </Text>
                    <VStack align="start" spacing={0}>
                      <Text fontSize="md">{selectedKeyForView.user_email}</Text>
                      <Text fontSize="sm" color="gray.500">@{selectedKeyForView.username}</Text>
                    </VStack>
                  </Box>

                  <Box gridColumn={{ base: "span 1", md: "span 2" }}>
                    <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={2}>
                      Permissions
                    </Text>
                    {selectedKeyForView.permissions.length > 0 ? (
                      <HStack flexWrap="wrap" spacing={2}>
                        {selectedKeyForView.permissions.map((perm) => (
                          <Badge key={perm} colorScheme="blue" fontSize="sm" p={2}>
                            {perm}
                          </Badge>
                        ))}
                      </HStack>
                    ) : (
                      <Text fontSize="sm" color="gray.500">No permissions assigned</Text>
                    )}
                  </Box>

                  <Box>
                    <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                      Status
                    </Text>
                    <Badge colorScheme={selectedKeyForView.is_active ? "green" : "red"} fontSize="sm" p={2}>
                      {selectedKeyForView.is_active ? "Active" : "Inactive"}
                    </Badge>
                  </Box>

                  <Box>
                    <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                      Created At
                    </Text>
                    <Text fontSize="sm">{new Date(selectedKeyForView.created_at).toLocaleString()}</Text>
                  </Box>

                  {selectedKeyForView.expires_at && (
                    <Box>
                      <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                        Expires At
                      </Text>
                      <Text fontSize="sm">{new Date(selectedKeyForView.expires_at).toLocaleString()}</Text>
                    </Box>
                  )}

                  {selectedKeyForView.last_used && (
                    <Box>
                      <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                        Last Used
                      </Text>
                      <Text fontSize="sm">{new Date(selectedKeyForView.last_used).toLocaleString()}</Text>
                    </Box>
                  )}

                  <Box>
                    <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                      Key ID
                    </Text>
                    <Text fontSize="sm" fontFamily="mono" color="gray.700">{selectedKeyForView.id}</Text>
                  </Box>
                </SimpleGrid>
              )}
            </ModalBody>
            <ModalFooter>
              <Button onClick={handleCloseViewModal}>Close</Button>
            </ModalFooter>
          </ModalContent>
        </Modal>

        {/* Update API Key Modal */}
        <Modal isOpen={isUpdateModalOpen} onClose={handleCloseUpdateModal} size="lg">
          <ModalOverlay />
          <ModalContent>
            <ModalHeader>Update API Key</ModalHeader>
            <ModalCloseButton />
            <ModalBody>
              <VStack spacing={4} align="stretch">
                <FormControl>
                  <FormLabel fontWeight="semibold">Key Name</FormLabel>
                  <Input
                    value={updateFormData.key_name || ""}
                    onChange={(e) => setUpdateFormData({ ...updateFormData, key_name: e.target.value })}
                    bg="white"
                  />
                </FormControl>

                <FormControl>
                  <FormLabel fontWeight="semibold">Status</FormLabel>
                  <Select
                    value={updateFormData.is_active ? "active" : "inactive"}
                    onChange={(e) => setUpdateFormData({ ...updateFormData, is_active: e.target.value === "active" })}
                    bg="white"
                  >
                    <option value="active">Active</option>
                    <option value="inactive">Inactive</option>
                  </Select>
                </FormControl>

                <FormControl>
                  <FormLabel fontWeight="semibold">Permissions</FormLabel>
                  <Text fontSize="sm" color="gray.600" mb={3}>
                    Select permissions for this API key
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
                        value={updateFormData.permissions || []}
                        onChange={(values) => setUpdateFormData({ ...updateFormData, permissions: values as string[] })}
                      >
                        <SimpleGrid columns={2} spacing={3}>
                          {permissions.map((perm) => (
                            <Checkbox key={perm} value={perm} colorScheme="blue">
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
                        Click &quot;Load Permissions&quot; in the Permissions tab to view available permissions
                      </AlertDescription>
                    </Alert>
                  )}
                </FormControl>

                {selectedKeyForUpdate && (
                  <Box>
                    <Text fontSize="sm" fontWeight="semibold" mb={2}>User: {selectedKeyForUpdate.user_email}</Text>
                    <Text fontSize="xs" color="gray.500">Key ID: {selectedKeyForUpdate.id}</Text>
                  </Box>
                )}
              </VStack>
            </ModalBody>
            <ModalFooter>
              <Button variant="ghost" mr={3} onClick={handleCloseUpdateModal} isDisabled={isUpdating}>
                Cancel
              </Button>
              <Button
                colorScheme="blue"
                onClick={handleUpdateApiKey}
                isLoading={isUpdating}
                loadingText="Updating..."
              >
                Update
              </Button>
            </ModalFooter>
          </ModalContent>
        </Modal>

        {/* Revoke API Key Alert Dialog */}
        <AlertDialog
          isOpen={isRevokeModalOpen}
          leastDestructiveRef={cancelRef}
          onClose={handleCloseRevokeModal}
        >
          <AlertDialogOverlay>
            <AlertDialogContent>
              <AlertDialogHeader fontSize="lg" fontWeight="bold">
                Revoke API Key
              </AlertDialogHeader>
              <AlertDialogBody>
                <VStack align="stretch" spacing={3}>
                  <Text>
                    Are you sure you want to revoke the API key &quot;{keyToRevoke?.key_name}&quot;?
                  </Text>
                  
                  <Box>
                    <Text fontWeight="semibold" fontSize="sm" color="gray.700" mb={2}>
                      Key Details:
                    </Text>
                    <VStack align="start" spacing={1} fontSize="sm">
                      <Text><strong>User:</strong> {keyToRevoke?.user_email} (@{keyToRevoke?.username})</Text>
                      <Text><strong>Key ID:</strong> {keyToRevoke?.id}</Text>
                      <Text><strong>Created:</strong> {keyToRevoke?.created_at ? new Date(keyToRevoke.created_at).toLocaleString() : "N/A"}</Text>
                    </VStack>
                  </Box>

                  {keyToRevoke && keyToRevoke.permissions.length > 0 && (
                    <Box>
                      <Text fontWeight="semibold" fontSize="sm" color="gray.700" mb={2}>
                        Permissions (will be revoked):
                      </Text>
                      <HStack flexWrap="wrap" spacing={2}>
                        {keyToRevoke.permissions.map((perm) => (
                          <Badge key={perm} colorScheme="orange" fontSize="xs">
                            {perm}
                          </Badge>
                        ))}
                      </HStack>
                    </Box>
                  )}

                  <Alert status="warning" borderRadius="md" mt={2}>
                    <AlertIcon />
                    <AlertDescription fontSize="sm">
                      This action will disable the API key and make it inactive. This action cannot be undone.
                    </AlertDescription>
                  </Alert>
                </VStack>
              </AlertDialogBody>
              <AlertDialogFooter>
                <Button ref={cancelRef} onClick={handleCloseRevokeModal} isDisabled={isRevoking}>
                  Cancel
                </Button>
                <Button
                  colorScheme="red"
                  onClick={handleRevokeApiKey}
                  ml={3}
                  isLoading={isRevoking}
                  loadingText="Revoking..."
                >
                  Revoke
                </Button>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialogOverlay>
        </AlertDialog>
      </ContentLayout>
    </>
  );
};

export default ProfilePage;
