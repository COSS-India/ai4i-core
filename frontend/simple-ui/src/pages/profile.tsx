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
  Code,
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
  useDisclosure,
  Progress,
  Divider,
} from "@chakra-ui/react";
import { ViewIcon, ViewOffIcon, CopyIcon } from "@chakra-ui/icons";
import { FiEdit2, FiCheck, FiX } from "react-icons/fi";
import Head from "next/head";
import React, { useState, useEffect, useRef } from "react";
import { useRouter } from "next/router";
import ContentLayout from "../components/common/ContentLayout";
import { useAuth } from "../hooks/useAuth";
import { useApiKey } from "../hooks/useApiKey";
import { useSessionExpiry } from "../hooks/useSessionExpiry";
import { User, UserUpdateRequest, Permission, APIKeyResponse, AdminAPIKeyWithUserResponse, APIKeyUpdate } from "../types/auth";
import roleService, { Role, UserRole } from "../services/roleService";
import authService from "../services/authService";
import {
  listAdopterTenants,
  updateTenant,
  registerTenant,
  Tenant,
  TenantUpdateRequest,
  TenantRegisterRequest,
  ListTenantsResponse,
} from "../services/tenantManagementService";
import { extractErrorInfo } from "../utils/errorHandler";

const ProfilePage: React.FC = () => {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading, updateUser } = useAuth();
  const { apiKey, getApiKey, setApiKey } = useApiKey();
  const { checkSessionExpiry } = useSessionExpiry();
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
  
  // Tenant Management state
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [isLoadingTenants, setIsLoadingTenants] = useState(false);
  const [selectedTenant, setSelectedTenant] = useState<Tenant | null>(null);
  const [isEditingTenant, setIsEditingTenant] = useState(false);
  const [tenantUpdateFormData, setTenantUpdateFormData] = useState<Partial<TenantUpdateRequest>>({});
  const [isUpdatingTenant, setIsUpdatingTenant] = useState(false);
  const [isCreatingTenant, setIsCreatingTenant] = useState(false);
  const [createTenantFormData, setCreateTenantFormData] = useState<Partial<TenantRegisterRequest>>({
    organization_name: "",
    domain: "",
    contact_email: "",
    requested_subscriptions: [],
  });
  const [subscriptionsInput, setSubscriptionsInput] = useState("tts, asr, nmt");
  const [quotaData, setQuotaData] = useState({
    characters_length: 100000,
    audio_length_in_min: 60,
  });
  const [updateQuotaData, setUpdateQuotaData] = useState({
    characters_length: 0,
    audio_length_in_min: 0,
  });
  const [updateUsageQuotaData, setUpdateUsageQuotaData] = useState({
    characters_length: 0,
    audio_length_in_min: 0,
  });
  const { isOpen: isTenantModalOpen, onOpen: onTenantModalOpen, onClose: onTenantModalClose } = useDisclosure();
  const { isOpen: isCreateTenantModalOpen, onOpen: onCreateTenantModalOpen, onClose: onCreateTenantModalClose } = useDisclosure();
  const tenantModalRef = useRef(null);
  
  // Usage tab state
  const [usageData, setUsageData] = useState<Tenant[]>([]);
  const [isLoadingUsage, setIsLoadingUsage] = useState(false);
  const createTenantModalRef = useRef(null);
  
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
  const tableRowHoverBg = useColorModeValue("gray.50", "gray.700");
  const costDetailsBg = useColorModeValue("blue.50", "blue.900");
  const totalRowBg = useColorModeValue("gray.50", "gray.700");

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

  // Redirect to auth page if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      // Store current path to redirect back after login
      if (typeof window !== 'undefined') {
        sessionStorage.setItem('redirectAfterAuth', '/profile');
      }
      router.push("/auth");
    }
  }, [isAuthenticated, authLoading, router]);

  // Fetch usage data when Usage tab is active
  useEffect(() => {
    if (!user || !user.id || !isAuthenticated) return;
    
    const isAdmin = user?.roles?.includes('ADMIN') || user?.is_superuser;
    const isModerator = user?.roles?.includes('MODERATOR');
    const usageTabIndex = isAdmin ? 7 : (isModerator ? 4 : 3);
    
    console.log("Usage tab check - activeTabIndex:", activeTabIndex, "usageTabIndex:", usageTabIndex, "hasData:", usageData.length > 0, "isLoading:", isLoadingUsage);
    
    // If Usage tab is active and we don't have data yet, fetch it
    if (activeTabIndex === usageTabIndex && usageData.length === 0 && !isLoadingUsage) {
      console.log("Usage tab is active, fetching usage data automatically");
      handleFetchUsage();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTabIndex, user, isAuthenticated]);

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
    // Check session expiry before performing action
    if (!checkSessionExpiry()) return;
    
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
    // Check session expiry before performing action
    if (!checkSessionExpiry()) return;
    
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
      // Indian phone number validation
      const phoneNumber = userFormData.phone_number.trim().replace(/\s+/g, '');
      
      // Remove common separators for validation
      const cleanedPhone = phoneNumber.replace(/[-\s()]/g, '');
      
      // Indian phone number patterns:
      // +91XXXXXXXXXX (13 digits: +91 + 10 digits)
      // 91XXXXXXXXXX (12 digits: 91 + 10 digits)
      // 0XXXXXXXXXX (11 digits: 0 + 10 digits)
      // XXXXXXXXXX (10 digits: just the number)
      
      let isValid = false;
      let digits = '';
      
      if (cleanedPhone.startsWith('+91')) {
        // Format: +91XXXXXXXXXX
        digits = cleanedPhone.substring(3);
        isValid = digits.length === 10 && /^[6-9]\d{9}$/.test(digits);
      } else if (cleanedPhone.startsWith('91') && cleanedPhone.length === 12) {
        // Format: 91XXXXXXXXXX
        digits = cleanedPhone.substring(2);
        isValid = /^[6-9]\d{9}$/.test(digits);
      } else if (cleanedPhone.startsWith('0') && cleanedPhone.length === 11) {
        // Format: 0XXXXXXXXXX
        digits = cleanedPhone.substring(1);
        isValid = /^[6-9]\d{9}$/.test(digits);
      } else if (cleanedPhone.length === 10) {
        // Format: XXXXXXXXXX (10 digits)
        digits = cleanedPhone;
        isValid = /^[6-9]\d{9}$/.test(digits);
      }
      
      if (!isValid) {
        newErrors.phone_number = "Invalid Indian phone number. Please enter a valid 10-digit mobile number (starting with 6-9) or use formats: +91XXXXXXXXXX, 91XXXXXXXXXX, 0XXXXXXXXXX, or XXXXXXXXXX";
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSaveUser = async () => {
    // Check session expiry before performing action
    if (!checkSessionExpiry()) return;
    
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

  const validatePhoneNumber = (phoneNumber: string): string | null => {
    if (!phoneNumber || phoneNumber.trim().length === 0) {
      return null; // Empty is valid (optional field)
    }
    
    const cleanedPhone = phoneNumber.trim().replace(/\s+/g, '').replace(/[-\s()]/g, '');
    let digits = '';
    
    if (cleanedPhone.startsWith('+91')) {
      digits = cleanedPhone.substring(3);
      if (digits.length === 10 && /^[6-9]\d{9}$/.test(digits)) {
        return null; // Valid
      }
    } else if (cleanedPhone.startsWith('91') && cleanedPhone.length === 12) {
      digits = cleanedPhone.substring(2);
      if (/^[6-9]\d{9}$/.test(digits)) {
        return null; // Valid
      }
    } else if (cleanedPhone.startsWith('0') && cleanedPhone.length === 11) {
      digits = cleanedPhone.substring(1);
      if (/^[6-9]\d{9}$/.test(digits)) {
        return null; // Valid
      }
    } else if (cleanedPhone.length === 10) {
      digits = cleanedPhone;
      if (/^[6-9]\d{9}$/.test(digits)) {
        return null; // Valid
      }
    }
    
    // Only show error if user has entered something substantial (more than 3 characters)
    if (cleanedPhone.length > 3) {
      return "Invalid Indian phone number. Please enter a valid 10-digit mobile number (starting with 6-9) or use formats: +91XXXXXXXXXX, 91XXXXXXXXXX, 0XXXXXXXXXX, or XXXXXXXXXX";
    }
    
    return null; // Don't show error for partial input
  };

  const handleInputChange = (field: keyof UserUpdateRequest, value: string | Record<string, any>) => {
    setUserFormData((prev) => ({
      ...prev,
      [field]: value,
    }));
    
    // Real-time validation for phone number
    if (field === 'phone_number' && typeof value === 'string') {
      const error = validatePhoneNumber(value);
      setErrors((prev) => {
        const newErrors = { ...prev };
        if (error) {
          newErrors.phone_number = error;
        } else {
          delete newErrors.phone_number;
        }
        return newErrors;
      });
    } else {
      // Clear error for other fields when user starts typing
    if (errors[field]) {
      setErrors((prev) => {
        const newErrors = { ...prev };
        delete newErrors[field];
        return newErrors;
      });
      }
    }
  };

  const maskedApiKey = apiKey ? "****" + apiKey.slice(-4) : "";

  // Function to fetch API keys from the API
  const handleFetchApiKeys = async () => {
    // Check session expiry before performing action
    if (!checkSessionExpiry()) return;
    
    console.log('Profile: Fetching API keys from /api/v1/auth/api-keys');
    setIsFetchingApiKey(true);
    setIsLoadingApiKeys(true);
    try {
      const response = await authService.listApiKeys();
      console.log('Profile: API keys fetched successfully:', response);
      const keys = Array.isArray(response.api_keys) ? response.api_keys : [];
      setApiKeys(keys);
      // Restore server-persisted selection so the correct key stays checked after login
      setSelectedApiKeyId(response.selected_api_key_id ?? null);
      
      toast({
        title: "API Keys Loaded",
        description: `Found ${keys?.length} API key(s)`,
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
        description: `Loaded ${allKeys?.length} API key(s)`,
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

  // Usage tab handler - handles both adopter admins and tenant users
  const handleFetchUsage = async () => {
    if (!user || !user.id) {
      console.warn("Cannot fetch usage: user or user.id is missing", { user });
      return;
    }
    
    console.log("handleFetchUsage called for user:", user.id, user.email, user.roles);
    setIsLoadingUsage(true);
    try {
      const { apiClient } = await import("../services/api");
      let tenants: Tenant[] = [];
      
      // Method 1: Try to get tenants as adopter admin
      try {
        const fetchedTenants = await listAdopterTenants();
        if (fetchedTenants && fetchedTenants.length > 0) {
          console.log("Found tenants via adopter admin endpoint:", fetchedTenants.length);
          setUsageData(fetchedTenants);
          setIsLoadingUsage(false);
          return;
        }
      } catch (adopterError: any) {
        console.log("Adopter admin endpoint failed:", adopterError.response?.status, adopterError.message);
      }
      
      // Method 2: Try to resolve tenant from user_id
      try {
        console.log("Attempting to resolve tenant for user_id:", user.id);
        const resolveResponse = await apiClient.get<{
          tenant_id: string;
          tenant_uuid: string;
          schema_name: string;
          subscriptions: string[];
          status: string;
        }>(`/api/v1/multi-tenant/resolve-tenant-from-user/${user.id}`);
        
        console.log("Resolve response:", resolveResponse.data);
        
        if (resolveResponse.data && resolveResponse.data.tenant_id) {
          // Get full tenant details using tenant_id
          const tenantResponse = await apiClient.get<Tenant>(
            `/api/v1/multi-tenant/view/tenant?tenant_id=${resolveResponse.data.tenant_id}`
          );
          
          if (tenantResponse.data) {
            console.log("Successfully fetched tenant:", tenantResponse.data.tenant_id);
            setUsageData([tenantResponse.data]);
            setIsLoadingUsage(false);
            return;
          }
        }
      } catch (resolveError: any) {
        console.error("Failed to resolve tenant for user:", resolveError.response?.status, resolveError.response?.data || resolveError.message);
      }
      
      // Method 3: If user is admin, try to list all tenants and find by email match
      if (user.roles?.includes('ADMIN') || user.is_superuser) {
        try {
          console.log("Trying to list all tenants and match by email:", user.email);
          const allTenantsResponse = await apiClient.get<ListTenantsResponse>('/api/v1/multi-tenant/list/tenants');
          
          if (allTenantsResponse.data && allTenantsResponse.data.tenants) {
            // Find tenant where contact_email matches user email
            const matchingTenant = allTenantsResponse.data.tenants.find(
              (t: Tenant) => t.email?.toLowerCase() === user.email?.toLowerCase()
            );
            
            if (matchingTenant) {
              console.log("Found tenant by email match:", matchingTenant.tenant_id);
              setUsageData([matchingTenant]);
              setIsLoadingUsage(false);
              return;
            }
          }
        } catch (listError: any) {
          console.error("Failed to list all tenants:", listError.response?.status, listError.message);
        }
      }
      
      // If all methods failed, show empty state
      console.warn("No tenant found for user:", user.id, user.email);
      setUsageData([]);
    } catch (error: any) {
      console.error("Failed to fetch usage data:", error);
      const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(error);
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMessage,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      setUsageData([]);
    } finally {
      setIsLoadingUsage(false);
    }
  };

  // Tenant Management handlers
  const handleFetchTenants = async () => {
    if (!user) return;
    
    setIsLoadingTenants(true);
    try {
      const fetchedTenants = await listAdopterTenants();
      setTenants(fetchedTenants);
    } catch (error: any) {
      console.error("Failed to fetch tenants:", error);
      const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(error);
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMessage,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      setTenants([]);
    } finally {
      setIsLoadingTenants(false);
    }
  };

  const handleEditTenant = (tenant: Tenant) => {
    if (!checkSessionExpiry()) return;
    
    setSelectedTenant(tenant);
    setTenantUpdateFormData({
      tenant_id: tenant.tenant_id,
      organization_name: tenant.organization_name,
      contact_email: tenant.email,
      domain: tenant.domain,
      requested_quotas: tenant.quotas || {},
      usage_quota: tenant.usage_quota || {},
    });
    // Initialize quota data for editing
    setUpdateQuotaData({
      characters_length: tenant.quotas?.characters_length || 0,
      audio_length_in_min: tenant.quotas?.audio_length_in_min || 0,
    });
    setUpdateUsageQuotaData({
      characters_length: tenant.usage_quota?.characters_length || 0,
      audio_length_in_min: tenant.usage_quota?.audio_length_in_min || 0,
    });
    setIsEditingTenant(true);
    onTenantModalOpen();
  };

  const handleCreateTenant = async () => {
    if (!createTenantFormData.organization_name || !createTenantFormData.domain || !createTenantFormData.contact_email) {
      toast({
        title: "Validation Error",
        description: "Please fill in all required fields (Organization Name, Domain, Contact Email).",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      return;
    }

    if (!checkSessionExpiry()) return;

    setIsCreatingTenant(true);
    try {
      // Parse subscriptions from input string
      const subscriptions = subscriptionsInput
        .split(",")
        .map((s) => s.trim())
        .filter((s) => s.length > 0);

      const registerPayload: TenantRegisterRequest = {
        organization_name: createTenantFormData.organization_name!,
        domain: createTenantFormData.domain!,
        contact_email: createTenantFormData.contact_email!,
        requested_subscriptions: subscriptions,
        requested_quotas: {
          characters_length: quotaData.characters_length,
          audio_length_in_min: quotaData.audio_length_in_min,
        },
        usage_quota: {
          characters_length: 0,
          audio_length_in_min: 0,
        },
      };

      const response = await registerTenant(registerPayload);
      
      toast({
        title: "Tenant Created",
        description: `Tenant "${response.tenant_id}" has been created successfully. Status: ${response.status}`,
        status: "success",
        duration: 5000,
        isClosable: true,
      });

      // Refresh tenants list
      await handleFetchTenants();
      
      onCreateTenantModalClose();
      setCreateTenantFormData({
        organization_name: "",
        domain: "",
        contact_email: "",
        requested_subscriptions: [],
      });
      setSubscriptionsInput("tts, asr, nmt");
      setQuotaData({
        characters_length: 100000,
        audio_length_in_min: 60,
      });
    } catch (error: any) {
      console.error("Failed to create tenant:", error);
      
      const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(error);
      
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMessage,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsCreatingTenant(false);
    }
  };

  const handleUpdateTenant = async () => {
    if (!selectedTenant || !tenantUpdateFormData.tenant_id) return;
    
    if (!checkSessionExpiry()) return;

    setIsUpdatingTenant(true);
    try {
      const updatePayload: TenantUpdateRequest = {
        tenant_id: tenantUpdateFormData.tenant_id,
      };

      // Only include fields that have been changed
      if (tenantUpdateFormData.organization_name !== selectedTenant.organization_name) {
        updatePayload.organization_name = tenantUpdateFormData.organization_name;
      }
      if (tenantUpdateFormData.contact_email !== selectedTenant.email) {
        updatePayload.contact_email = tenantUpdateFormData.contact_email;
      }
      if (tenantUpdateFormData.domain !== selectedTenant.domain) {
        updatePayload.domain = tenantUpdateFormData.domain;
      }
      // Use quota data from state instead of tenantUpdateFormData
      const newQuotas = {
        characters_length: updateQuotaData.characters_length,
        audio_length_in_min: updateQuotaData.audio_length_in_min,
      };
      if (JSON.stringify(newQuotas) !== JSON.stringify(selectedTenant.quotas || {})) {
        updatePayload.requested_quotas = newQuotas;
      }
      
      const newUsageQuota = {
        characters_length: updateUsageQuotaData.characters_length,
        audio_length_in_min: updateUsageQuotaData.audio_length_in_min,
      };
      if (JSON.stringify(newUsageQuota) !== JSON.stringify(selectedTenant.usage_quota || {})) {
        updatePayload.usage_quota = newUsageQuota;
      }

      const response = await updateTenant(updatePayload);
      
      toast({
        title: "Tenant Updated",
        description: response.message,
        status: "success",
        duration: 5000,
        isClosable: true,
      });

      // Refresh tenants list
      await handleFetchTenants();
      
      setIsEditingTenant(false);
      onTenantModalClose();
      setSelectedTenant(null);
      setTenantUpdateFormData({});
      setUpdateQuotaData({
        characters_length: 0,
        audio_length_in_min: 0,
      });
      setUpdateUsageQuotaData({
        characters_length: 0,
        audio_length_in_min: 0,
      });
    } catch (error: any) {
      console.error("Failed to update tenant:", error);
      const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(error);
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMessage,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsUpdatingTenant(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status?.toUpperCase()) {
      case "ACTIVE":
        return "green";
      case "PENDING":
        return "yellow";
      case "SUSPENDED":
        return "red";
      case "DEACTIVATED":
        return "gray";
      default:
        return "gray";
    }
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
        <Center h="400px">
          <VStack spacing={4}>
            <Spinner size="xl" color="orange.500" />
            <Text color="gray.600">Redirecting to sign in...</Text>
          </VStack>
        </Center>
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
          <Heading size="xl" mb={8} color="gray.800" userSelect="none" cursor="default" tabIndex={-1}>
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
                // Calculate tab index: User Details(0), Organization(1), API Key(2), Roles(3 if admin), Create API Key(4 if admin), API Key Management(5 if admin, 3 if moderator only), Tenant Management(6 if admin only)
                const apiKeyManagementTabIndex = isAdmin ? 5 : (isModerator ? 3 : -1);
                const tenantManagementTabIndex = isAdmin ? 6 : -1;
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
                // When Tenant Management tab is clicked, fetch tenants
                if (index === tenantManagementTabIndex) {
                  console.log('Profile: Tenant Management tab clicked, fetching tenants');
                  handleFetchTenants();
                }
                // When Usage tab is clicked, fetch usage data
                // Tab order: User Details(0), Organization(1), API Key(2), 
                //            Roles(3 if admin), Create API Key(4 if admin), 
                //            API Key Management(5 if admin, 3 if moderator only), 
                //            Tenant Management(6 if admin only), Usage(last)
                const usageTabIndex = isAdmin ? 7 : (isModerator ? 4 : 3);
                if (index === usageTabIndex) {
                  console.log('Profile: Usage tab clicked, fetching usage data for user:', user.id, user.email);
                  handleFetchUsage();
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
                {(user?.roles?.includes('ADMIN') || user?.is_superuser) && (
                  <Tab fontWeight="semibold">Tenant Management</Tab>
                )}
                <Tab fontWeight="semibold">Usage</Tab>
              </TabList>

              <TabPanels>
                {/* User Details Tab */}
                <TabPanel px={0} pt={6}>
                  <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
                    <CardHeader>
                      <HStack justify="space-between">
                        <Heading size="md" color="gray.700" userSelect="none" cursor="default">
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
                      placeholder="+91XXXXXXXXXX or XXXXXXXXXX"
                      type="tel"
                    />
                    {isEditingUser && !errors.phone_number && (
                      <Text fontSize="xs" color="gray.500" mt={1}>
                        Enter a valid Indian mobile number (10 digits starting with 6-9)
                      </Text>
                    )}
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
                      <Heading size="md" color="gray.700" userSelect="none" cursor="default">
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
                        <Heading size="md" color="gray.700" userSelect="none" cursor="default">
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
                          <Heading size="sm" mb={4} color="gray.700" userSelect="none" cursor="default">
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
                                          onChange={async (e) => {
                                            if (e.target.checked) {
                                              try {
                                                await authService.selectApiKey(key.id);
                                                setSelectedApiKeyId(key.id);
                                                if (key.key_value) {
                                                  setApiKey(key.key_value);
                                                }
                                                toast({
                                                  title: "API Key Selected",
                                                  description: key.key_value
                                                    ? `API key "${key.key_name}" has been set as your current key`
                                                    : `API key "${key.key_name}" is now selected. Key value is not available (only shown once on creation).`,
                                                  status: key.key_value ? "success" : "info",
                                                  duration: key.key_value ? 3000 : 4000,
                                                  isClosable: true,
                                                });
                                              } catch (err) {
                                                toast({
                                                  title: "Error",
                                                  description: err instanceof Error ? err.message : "Failed to save selected API key",
                                                  status: "error",
                                                  duration: 5000,
                                                  isClosable: true,
                                                });
                                              }
                                            } else {
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
                        <Heading size="md" color="gray.700" userSelect="none" cursor="default">
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
                            <Heading size="sm" mb={4} color="gray.700" userSelect="none" cursor="default">
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
                              <Heading size="sm" mb={4} color="gray.700" userSelect="none" cursor="default">
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
                              <Heading size="sm" mb={4} color="gray.700" userSelect="none" cursor="default">
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
                              <Heading size="sm" mb={4} color="gray.700" userSelect="none" cursor="default">
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
                        <Heading size="md" color="gray.700" userSelect="none" cursor="default">
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
                            <Heading size="sm" mb={4} color="gray.700" userSelect="none" cursor="default">
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
                              <Heading size="sm" mb={4} color="gray.700" userSelect="none" cursor="default">
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
                              <Heading size="sm" mb={4} color="gray.700" userSelect="none" cursor="default">
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
                                      
                                      // Refresh API keys list to include the new key (do not change selection)
                                      try {
                                        const listResponse = await authService.listApiKeys();
                                        setApiKeys(Array.isArray(listResponse.api_keys) ? listResponse.api_keys : []);
                                        setSelectedApiKeyId(listResponse.selected_api_key_id ?? null);
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
                          <Heading size="md" color="gray.700" userSelect="none" cursor="default">
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
                              <Heading size="sm" color="gray.700" userSelect="none" cursor="default">Filters</Heading>
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
                {/* Tenant Management Tab - Only for Admin */}
                {(user?.roles?.includes('ADMIN') || user?.is_superuser) && (
                  <TabPanel px={0} pt={6}>
                  <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
                    <CardHeader>
                      <HStack justify="space-between" align="flex-start">
                        <Box>
                          <Heading size="md" color="gray.700" userSelect="none" cursor="default">
                            Tenant Management
                          </Heading>
                          <Text fontSize="sm" color="gray.600" mt={2}>
                            Manage your tenants as an Adopter Admin. View and update tenant information.
                          </Text>
                        </Box>
                        <Button
                          colorScheme="green"
                          size="sm"
                          onClick={onCreateTenantModalOpen}
                          leftIcon={<Text>+</Text>}
                        >
                          Create Tenant
                        </Button>
                      </HStack>
                    </CardHeader>
                    <CardBody>
                      {isLoadingTenants ? (
                        <Center py={8}>
                          <Spinner size="xl" color="blue.500" />
                        </Center>
                      ) : tenants.length === 0 ? (
                        <Alert status="info">
                          <AlertIcon />
                          <AlertDescription>
                            No tenants found. You need to be an adopter admin (own at least one tenant) to see tenants here.
                          </AlertDescription>
                        </Alert>
                      ) : (
                        <Box overflowX="auto">
                          <Table variant="simple" size="sm">
                            <Thead>
                              <Tr>
                                <Th>Tenant ID</Th>
                                <Th>Organization</Th>
                                <Th>Email</Th>
                                <Th>Domain</Th>
                                <Th>Status</Th>
                                <Th>Subscriptions</Th>
                                <Th>Created</Th>
                                <Th>Actions</Th>
                              </Tr>
                            </Thead>
                            <Tbody>
                              {tenants.map((tenant) => (
                                <Tr
                                  key={tenant.id}
                                  _hover={{ bg: tableRowHoverBg, cursor: "pointer" }}
                                >
                                  <Td>
                                    <Text fontWeight="medium" fontSize="sm">
                                      {tenant.tenant_id}
                                    </Text>
                                  </Td>
                                  <Td>
                                    <Text fontSize="sm">{tenant.organization_name}</Text>
                                  </Td>
                                  <Td>
                                    <Text fontSize="sm">{tenant.email}</Text>
                                  </Td>
                                  <Td>
                                    <Text fontSize="sm" fontFamily="mono">
                                      {tenant.domain}
                                    </Text>
                                  </Td>
                                  <Td>
                                    <Badge
                                      colorScheme={getStatusColor(tenant.status)}
                                      fontSize="xs"
                                    >
                                      {tenant.status}
                                    </Badge>
                                  </Td>
                                  <Td>
                                    <HStack spacing={1} flexWrap="wrap">
                                      {tenant.subscriptions && tenant.subscriptions.length > 0 ? (
                                        tenant.subscriptions.map((sub, idx) => (
                                          <Badge key={idx} colorScheme="blue" fontSize="xs">
                                            {sub}
                                          </Badge>
                                        ))
                                      ) : (
                                        <Text fontSize="xs" color="gray.500">
                                          None
                                        </Text>
                                      )}
                                    </HStack>
                                  </Td>
                                  <Td>
                                    <Text fontSize="xs" color="gray.600">
                                      {new Date(tenant.created_at).toLocaleDateString()}
                                    </Text>
                                  </Td>
                                  <Td>
                                    <Button
                                      size="xs"
                                      colorScheme="blue"
                                      onClick={() => handleEditTenant(tenant)}
                                    >
                                      Update
                                    </Button>
                                  </Td>
                                </Tr>
                              ))}
                            </Tbody>
                          </Table>
                        </Box>
                      )}
                    </CardBody>
                  </Card>
                  </TabPanel>
                )}
                
                {/* Usage Tab - Visible to all authenticated users */}
                <TabPanel px={0} pt={6}>
                  <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
                    <CardHeader>
                      <Heading size="md" color="gray.700" userSelect="none" cursor="default">
                        Usage & Quotas
                      </Heading>
                      <Text fontSize="sm" color="gray.600" mt={2}>
                        View your quota limits and current usage across all tenants.
                      </Text>
                    </CardHeader>
                    <CardBody>
                      {isLoadingUsage ? (
                        <Center py={8}>
                          <VStack spacing={4}>
                            <Spinner size="xl" color="blue.500" />
                            <Text color="gray.600">Loading usage data...</Text>
                          </VStack>
                        </Center>
                      ) : usageData.length === 0 ? (
                        <Alert status="info">
                          <AlertIcon />
                          <AlertDescription>
                            No tenant data found. You need to be an adopter admin (own at least one tenant) to see usage information here.
                          </AlertDescription>
                        </Alert>
                      ) : (
                        <VStack spacing={6} align="stretch">
                          {usageData.map((tenant) => {
                            const quotaChars = tenant.quotas?.characters_length || 0;
                            const quotaAudio = tenant.quotas?.audio_length_in_min || 0;
                            const usageChars = tenant.usage_quota?.characters_length || 0;
                            const usageAudio = tenant.usage_quota?.audio_length_in_min || 0;
                            const charsPercent = quotaChars > 0 ? Math.min((usageChars / quotaChars) * 100, 100) : 0;
                            const audioPercent = quotaAudio > 0 ? Math.min((usageAudio / quotaAudio) * 100, 100) : 0;
                            
                            // Pricing constants
                            const CHAR_RATE_PER_1K = 10; // ₹10 per 1,000 characters (for both NMT and TTS)
                            const AUDIO_RATE_PER_MIN = 1; // ₹1 per minute (for ASR)
                            
                            // Calculate costs by resource type (not by service)
                            // Characters are used by both NMT and TTS
                            const charsCost = usageChars > 0 ? (usageChars * CHAR_RATE_PER_1K) / 1000 : 0;
                            // Audio minutes are used by ASR
                            const audioCost = usageAudio > 0 ? usageAudio * AUDIO_RATE_PER_MIN : 0;
                            const totalCost = charsCost + audioCost;
                            
                            // Check if tenant has any relevant subscriptions
                            const subscriptions = tenant.subscriptions || [];
                            const hasCharServices = subscriptions.some(sub => ['nmt', 'tts'].includes(sub));
                            const hasAudioServices = subscriptions.includes('asr');
                            
                            return (
                              <Box
                                key={tenant.id}
                                borderWidth="1px"
                                borderRadius="md"
                                p={6}
                                bg="white"
                                borderColor={cardBorder}
                              >
                                <VStack spacing={4} align="stretch">
                                  <Box>
                                    <Heading size="sm" color="gray.700" mb={1}>
                                      {tenant.organization_name}
                                    </Heading>
                                    <Text fontSize="xs" color="gray.500">
                                      {tenant.tenant_id} • {tenant.domain}
                                    </Text>
                                  </Box>
                                  
                                  <Divider />
                                  
                                  {/* Characters Length Usage */}
                                  <Box>
                                    <HStack justify="space-between" mb={2}>
                                      <FormLabel fontSize="sm" fontWeight="semibold" mb={0}>
                                        Characters Length
                                      </FormLabel>
                                      <Text fontSize="sm" color="gray.600">
                                        {usageChars.toLocaleString()} / {quotaChars.toLocaleString()}
                                      </Text>
                                    </HStack>
                                    <Progress
                                      value={charsPercent}
                                      colorScheme={charsPercent >= 90 ? "red" : charsPercent >= 70 ? "yellow" : "green"}
                                      size="lg"
                                      borderRadius="md"
                                    />
                                    <Text fontSize="xs" color="gray.500" mt={1}>
                                      {charsPercent.toFixed(1)}% used
                                    </Text>
                                  </Box>
                                  
                                  {/* Audio Length Usage */}
                                  <Box>
                                    <HStack justify="space-between" mb={2}>
                                      <FormLabel fontSize="sm" fontWeight="semibold" mb={0}>
                                        Audio Length (minutes)
                                      </FormLabel>
                                      <Text fontSize="sm" color="gray.600">
                                        {usageAudio.toLocaleString()} / {quotaAudio.toLocaleString()}
                                      </Text>
                                    </HStack>
                                    <Progress
                                      value={audioPercent}
                                      colorScheme={audioPercent >= 90 ? "red" : audioPercent >= 70 ? "yellow" : "green"}
                                      size="lg"
                                      borderRadius="md"
                                    />
                                    <Text fontSize="xs" color="gray.500" mt={1}>
                                      {audioPercent.toFixed(1)}% used
                                    </Text>
                                  </Box>
                                  
                                  {/* Subscriptions */}
                                  {tenant.subscriptions && tenant.subscriptions.length > 0 && (
                                    <Box>
                                      <FormLabel fontSize="sm" fontWeight="semibold" mb={2}>
                                        Active Subscriptions
                                      </FormLabel>
                                      <HStack spacing={2} flexWrap="wrap">
                                        {tenant.subscriptions.map((sub, idx) => (
                                          <Badge key={idx} colorScheme="blue" fontSize="xs">
                                            {sub.toUpperCase()}
                                          </Badge>
                                        ))}
                                      </HStack>
                                    </Box>
                                  )}
                                  
                                  {/* Usage-Based Pricing & Cost Breakdown */}
                                  <Divider />
                                  <Box>
                                    <Heading size="sm" color="gray.700" mb={4}>
                                      Usage-Based Pricing & Cost Breakdown
                                    </Heading>
                                    
                                    <TableContainer>
                                      <Table variant="simple" size="sm">
                                        <Thead>
                                          <Tr>
                                            <Th>Resource Type</Th>
                                            <Th isNumeric>Usage</Th>
                                            <Th>Rate</Th>
                                            <Th isNumeric>Cost</Th>
                                          </Tr>
                                        </Thead>
                                        <Tbody>
                                          {usageChars > 0 && (
                                            <Tr>
                                              <Td fontWeight="medium">Characters</Td>
                                              <Td isNumeric>{usageChars.toLocaleString()} chars</Td>
                                              <Td>₹{CHAR_RATE_PER_1K}/1K chars</Td>
                                              <Td isNumeric fontWeight="semibold">₹{charsCost.toFixed(2)}</Td>
                                            </Tr>
                                          )}
                                          {usageAudio > 0 && (
                                            <Tr>
                                              <Td fontWeight="medium">Audio</Td>
                                              <Td isNumeric>{usageAudio.toLocaleString()} min</Td>
                                              <Td>₹{AUDIO_RATE_PER_MIN}/min</Td>
                                              <Td isNumeric fontWeight="semibold">₹{audioCost.toFixed(2)}</Td>
                                            </Tr>
                                          )}
                                          {usageChars === 0 && usageAudio === 0 && (
                                            <Tr>
                                              <Td colSpan={4} textAlign="center" color="gray.500" fontSize="sm">
                                                No usage recorded yet
                                              </Td>
                                            </Tr>
                                          )}
                                          {(usageChars > 0 || usageAudio > 0) && (
                                            <Tr bg={totalRowBg}>
                                              <Td fontWeight="bold">Total</Td>
                                              <Td></Td>
                                              <Td></Td>
                                              <Td isNumeric fontWeight="bold" fontSize="md">
                                                ₹{totalCost.toFixed(2)}
                                              </Td>
                                            </Tr>
                                          )}
                                        </Tbody>
                                      </Table>
                                    </TableContainer>
                                    
                                    {/* Cost Calculation Details */}
                                    {(usageChars > 0 || usageAudio > 0) && (
                                      <Box mt={4} p={4} bg={costDetailsBg} borderRadius="md">
                                        <Text fontSize="sm" fontWeight="semibold" mb={2} color="gray.700">
                                          Cost Calculation Details:
                                        </Text>
                                        <VStack align="stretch" spacing={1} fontSize="xs">
                                          {usageChars > 0 && (
                                            <Text color="gray.600">
                                              <strong>Characters:</strong> ({usageChars.toLocaleString()} chars × ₹{CHAR_RATE_PER_1K}/1K) / 1,000 = ₹{charsCost.toFixed(2)}
                                            </Text>
                                          )}
                                          {usageAudio > 0 && (
                                            <Text color="gray.600">
                                              <strong>Audio:</strong> {usageAudio.toLocaleString()} min × ₹{AUDIO_RATE_PER_MIN}/min = ₹{audioCost.toFixed(2)}
                                            </Text>
                                          )}
                                        </VStack>
                                      </Box>
                                    )}
                                  </Box>
                                </VStack>
                              </Box>
                            );
                          })}
                        </VStack>
                      )}
                    </CardBody>
                  </Card>
                </TabPanel>
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

        {/* Create Tenant Modal */}
        <Modal
          isOpen={isCreateTenantModalOpen}
          onClose={onCreateTenantModalClose}
          size="xl"
          initialFocusRef={createTenantModalRef}
        >
          <ModalOverlay />
          <ModalContent>
            <ModalHeader>Create New Tenant</ModalHeader>
            <ModalCloseButton />
            <ModalBody pb={6}>
              <VStack spacing={4} align="stretch">
                <FormControl isRequired>
                  <FormLabel>Organization Name</FormLabel>
                  <Input
                    ref={createTenantModalRef}
                    value={createTenantFormData.organization_name || ""}
                    onChange={(e) =>
                      setCreateTenantFormData({
                        ...createTenantFormData,
                        organization_name: e.target.value,
                      })
                    }
                    placeholder="Enter organization name"
                  />
                </FormControl>

                <FormControl isRequired>
                  <FormLabel>Domain</FormLabel>
                  <Input
                    value={createTenantFormData.domain || ""}
                    onChange={(e) =>
                      setCreateTenantFormData({
                        ...createTenantFormData,
                        domain: e.target.value,
                      })
                    }
                    placeholder="Enter domain (e.g., acme.com)"
                  />
                </FormControl>

                <FormControl isRequired>
                  <FormLabel>Contact Email</FormLabel>
                  <Input
                    type="email"
                    value={createTenantFormData.contact_email || ""}
                    onChange={(e) =>
                      setCreateTenantFormData({
                        ...createTenantFormData,
                        contact_email: e.target.value,
                      })
                    }
                    placeholder="Enter contact email"
                  />
                </FormControl>

                <FormControl>
                  <FormLabel>Requested Subscriptions (comma-separated)</FormLabel>
                  <Input
                    value={subscriptionsInput}
                    onChange={(e) => setSubscriptionsInput(e.target.value)}
                    placeholder="e.g., tts, asr, nmt"
                  />
                  <Text fontSize="xs" color="gray.600" mt={1}>
                    Enter service names separated by commas (e.g., tts, asr, nmt). Default: tts, asr, nmt
                  </Text>
                </FormControl>

                <FormControl>
                  <FormLabel>Requested Quotas (Optional)</FormLabel>
                  <SimpleGrid columns={2} spacing={4} mt={2}>
                    <FormControl>
                      <FormLabel fontSize="sm">Characters Length</FormLabel>
                      <Input
                        type="number"
                        value={quotaData.characters_length}
                        onChange={(e) =>
                          setQuotaData({
                            ...quotaData,
                            characters_length: parseInt(e.target.value) || 0,
                          })
                        }
                        placeholder="100000"
                        min={0}
                      />
                    </FormControl>
                    <FormControl>
                      <FormLabel fontSize="sm">Audio Length (minutes)</FormLabel>
                      <Input
                        type="number"
                        value={quotaData.audio_length_in_min}
                        onChange={(e) =>
                          setQuotaData({
                            ...quotaData,
                            audio_length_in_min: parseInt(e.target.value) || 0,
                          })
                        }
                        placeholder="60"
                        min={0}
                      />
                    </FormControl>
                  </SimpleGrid>
                  <Text fontSize="xs" color="gray.600" mt={2}>
                    Set quota limits for the tenant. Default: 100,000 characters and 60 minutes of audio.
                  </Text>
                </FormControl>
              </VStack>
            </ModalBody>

            <ModalFooter>
              <Button
                colorScheme="green"
                mr={3}
                onClick={handleCreateTenant}
                isLoading={isCreatingTenant}
                loadingText="Creating"
              >
                Create Tenant
              </Button>
              <Button onClick={onCreateTenantModalClose} isDisabled={isCreatingTenant}>
                Cancel
              </Button>
            </ModalFooter>
          </ModalContent>
        </Modal>

        {/* Tenant Management Modal */}
        <Modal
          isOpen={isTenantModalOpen}
          onClose={() => {
            onTenantModalClose();
            setUpdateQuotaData({
              characters_length: 0,
              audio_length_in_min: 0,
            });
            setUpdateUsageQuotaData({
              characters_length: 0,
              audio_length_in_min: 0,
            });
          }}
          size="xl"
          initialFocusRef={tenantModalRef}
        >
          <ModalOverlay />
          <ModalContent>
            <ModalHeader>Update Tenant</ModalHeader>
            <ModalCloseButton />
            <ModalBody pb={6}>
              {selectedTenant && (
                <VStack spacing={4} align="stretch">
                  <FormControl>
                    <FormLabel>Tenant ID</FormLabel>
                    <Input
                      value={selectedTenant.tenant_id}
                      isReadOnly
                      bg={inputReadOnlyBg}
                      fontSize="sm"
                    />
                  </FormControl>

                  <FormControl>
                    <FormLabel>Organization Name</FormLabel>
                    <Input
                      ref={tenantModalRef}
                      value={tenantUpdateFormData.organization_name || ""}
                      onChange={(e) =>
                        setTenantUpdateFormData({
                          ...tenantUpdateFormData,
                          organization_name: e.target.value,
                        })
                      }
                      placeholder="Enter organization name"
                    />
                  </FormControl>

                  <FormControl>
                    <FormLabel>Contact Email</FormLabel>
                    <Input
                      type="email"
                      value={tenantUpdateFormData.contact_email || ""}
                      onChange={(e) =>
                        setTenantUpdateFormData({
                          ...tenantUpdateFormData,
                          contact_email: e.target.value,
                        })
                      }
                      placeholder="Enter contact email"
                    />
                  </FormControl>

                  <FormControl>
                    <FormLabel>Domain</FormLabel>
                    <Input
                      value={tenantUpdateFormData.domain || ""}
                      onChange={(e) =>
                        setTenantUpdateFormData({
                          ...tenantUpdateFormData,
                          domain: e.target.value,
                        })
                      }
                      placeholder="Enter domain"
                    />
                  </FormControl>

                  <FormControl>
                    <FormLabel>Requested Quotas</FormLabel>
                    <SimpleGrid columns={2} spacing={4} mt={2}>
                      <FormControl>
                        <FormLabel fontSize="sm">Characters Length</FormLabel>
                        <Input
                          type="number"
                          value={updateQuotaData.characters_length}
                          onChange={(e) =>
                            setUpdateQuotaData({
                              ...updateQuotaData,
                              characters_length: parseInt(e.target.value) || 0,
                            })
                          }
                          placeholder="100000"
                          min={0}
                        />
                      </FormControl>
                      <FormControl>
                        <FormLabel fontSize="sm">Audio Length (minutes)</FormLabel>
                        <Input
                          type="number"
                          value={updateQuotaData.audio_length_in_min}
                          onChange={(e) =>
                            setUpdateQuotaData({
                              ...updateQuotaData,
                              audio_length_in_min: parseInt(e.target.value) || 0,
                            })
                          }
                          placeholder="60"
                          min={0}
                        />
                      </FormControl>
                    </SimpleGrid>
                    <Text fontSize="xs" color="gray.600" mt={2}>
                      Set quota limits for the tenant. You can increase or decrease these values.
                    </Text>
                  </FormControl>

                  <FormControl>
                    <FormLabel>Usage Quota</FormLabel>
                    <SimpleGrid columns={2} spacing={4} mt={2}>
                      <FormControl>
                        <FormLabel fontSize="sm">Characters Length Used</FormLabel>
                        <Input
                          type="number"
                          value={updateUsageQuotaData.characters_length}
                          onChange={(e) =>
                            setUpdateUsageQuotaData({
                              ...updateUsageQuotaData,
                              characters_length: parseInt(e.target.value) || 0,
                            })
                          }
                          placeholder="0"
                          min={0}
                        />
                      </FormControl>
                      <FormControl>
                        <FormLabel fontSize="sm">Audio Length Used (minutes)</FormLabel>
                        <Input
                          type="number"
                          value={updateUsageQuotaData.audio_length_in_min}
                          onChange={(e) =>
                            setUpdateUsageQuotaData({
                              ...updateUsageQuotaData,
                              audio_length_in_min: parseInt(e.target.value) || 0,
                            })
                          }
                          placeholder="0"
                          min={0}
                        />
                      </FormControl>
                    </SimpleGrid>
                    <Text fontSize="xs" color="gray.600" mt={2}>
                      Current usage quota values. You can update these to reflect actual usage.
                    </Text>
                  </FormControl>
                </VStack>
              )}
            </ModalBody>

            <ModalFooter>
              <Button
                colorScheme="blue"
                mr={3}
                onClick={handleUpdateTenant}
                isLoading={isUpdatingTenant}
                loadingText="Updating"
              >
                Update Tenant
              </Button>
              <Button onClick={onTenantModalClose} isDisabled={isUpdatingTenant}>
                Cancel
              </Button>
            </ModalFooter>
          </ModalContent>
        </Modal>
      </ContentLayout>
    </>
  );
};

export default ProfilePage;
