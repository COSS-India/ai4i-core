// Tenant Management page for Adopter Admin - list and update tenants

import {
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  FormControl,
  FormLabel,
  Heading,
  Input,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Badge,
  Text,
  VStack,
  HStack,
  useColorModeValue,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
  useToast,
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalFooter,
  ModalBody,
  ModalCloseButton,
  useDisclosure,
  Spinner,
  Center,
  Alert,
  AlertIcon,
  AlertDescription,
  Code,
  SimpleGrid,
} from "@chakra-ui/react";
import Head from "next/head";
import { useRouter } from "next/router";
import React, { useState, useEffect, useRef } from "react";
import ContentLayout from "../components/common/ContentLayout";
import {
  listAdopterTenants,
  updateTenant,
  registerTenant,
  resendVerificationEmail,
  verifyTenantEmail,
  Tenant,
  TenantUpdateRequest,
  TenantRegisterRequest,
} from "../services/tenantManagementService";
import { useAuth } from "../hooks/useAuth";
import { useSessionExpiry } from "../hooks/useSessionExpiry";
import { extractErrorInfo } from "../utils/errorHandler";

const TenantManagementPage: React.FC = () => {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedTenant, setSelectedTenant] = useState<Tenant | null>(null);
  const [isEditingTenant, setIsEditingTenant] = useState(false);
  const [updateFormData, setUpdateFormData] = useState<Partial<TenantUpdateRequest>>({});
  const [isUpdating, setIsUpdating] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [isResendingVerification, setIsResendingVerification] = useState<string | null>(null);
  const [verificationTokens, setVerificationTokens] = useState<Record<string, string>>({});
  const [createFormData, setCreateFormData] = useState<Partial<TenantRegisterRequest>>({
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
  const [activeTab, setActiveTab] = useState(0);
  const toast = useToast();
  const { user } = useAuth();
  const router = useRouter();
  const { checkSessionExpiry } = useSessionExpiry();
  const { isOpen, onOpen, onClose } = useDisclosure();
  const { isOpen: isCreateOpen, onOpen: onCreateOpen, onClose: onCreateClose } = useDisclosure();
  const initialRef = useRef(null);
  const createInitialRef = useRef(null);

  const bgColor = useColorModeValue("white", "gray.800");
  const borderColor = useColorModeValue("gray.200", "gray.700");
  const tableRowHoverBg = useColorModeValue("gray.50", "gray.700");

  // Check if user is authenticated
  useEffect(() => {
    if (!user) {
      toast({
        title: "Authentication Required",
        description: "Please log in to access Tenant Management.",
        status: "warning",
        duration: 5000,
        isClosable: true,
      });
      router.push('/auth');
    }
  }, [user, router, toast]);

  // Fetch tenants on component mount
  useEffect(() => {
    const fetchTenants = async () => {
      if (!user) return;
      
      setIsLoading(true);
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
        setIsLoading(false);
      }
    };

    fetchTenants();
  }, [user, toast]);

  const handleEditTenant = (tenant: Tenant) => {
    if (!checkSessionExpiry()) return;
    
    setSelectedTenant(tenant);
    setUpdateFormData({
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
    onOpen();
  };

  const handleCreateTenant = async () => {
    if (!createFormData.organization_name || !createFormData.domain || !createFormData.contact_email) {
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

    setIsCreating(true);
    try {
      // Parse subscriptions from input string
      const subscriptions = subscriptionsInput
        .split(",")
        .map((s) => s.trim())
        .filter((s) => s.length > 0);

      const registerPayload: TenantRegisterRequest = {
        organization_name: createFormData.organization_name!,
        domain: createFormData.domain!,
        contact_email: createFormData.contact_email!,
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
      
      if (response.status === "PENDING" && response.token) {
        // Show verification token for pending tenants
        const verificationUrl = `${window.location.origin}/api/v1/multi-tenant/email/verify?token=${response.token}`;
        // Store token for this tenant
        setVerificationTokens(prev => ({ ...prev, [response.tenant_id]: response.token! }));
        toast({
          title: "Tenant Created - Verification Required",
          description: `Tenant "${response.tenant_id}" created with status PENDING. Use "Resend Verification" button to get verification link. Token: ${response.token.substring(0, 20)}...`,
          status: "warning",
          duration: 10000,
          isClosable: true,
        });
      } else {
        toast({
          title: "Tenant Created",
          description: `Tenant "${response.tenant_id}" has been created successfully. Status: ${response.status}`,
          status: "success",
          duration: 5000,
          isClosable: true,
        });
      }

      // Refresh tenants list
      const fetchedTenants = await listAdopterTenants();
      setTenants(fetchedTenants);
      
      onCreateClose();
      setCreateFormData({
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
      setIsCreating(false);
    }
  };

  const handleResendVerification = async (tenantId: string) => {
    if (!checkSessionExpiry()) return;

    setIsResendingVerification(tenantId);
    try {
      const response = await resendVerificationEmail(tenantId);
      
      const verificationUrl = `${window.location.origin}/api/v1/multi-tenant/email/verify?token=${response.token}`;
      toast({
        title: "Verification Email Resent",
        description: `Verification email resent. Token: ${response.token.substring(0, 20)}... Click "Verify Now" button or visit: ${verificationUrl}`,
        status: "info",
        duration: 10000,
        isClosable: true,
      });
      
      // Store token for this specific tenant
      setVerificationTokens(prev => ({ ...prev, [tenantId]: response.token }));
    } catch (error: any) {
      console.error("Failed to resend verification email:", error);
      
      const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(error);
      
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMessage,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsResendingVerification(null);
    }
  };

  const handleVerifyEmail = async (token: string, tenantId?: string) => {
    if (!checkSessionExpiry()) return;

    try {
      await verifyTenantEmail(token);
      
      toast({
        title: "Email Verified",
        description: "Tenant email has been verified successfully. Tenant is now ACTIVE.",
        status: "success",
        duration: 5000,
        isClosable: true,
      });

      // Refresh tenants list
      const fetchedTenants = await listAdopterTenants();
      setTenants(fetchedTenants);
      
      // Clear token after successful verification
      if (tenantId) {
        setVerificationTokens(prev => {
          const newTokens = { ...prev };
          delete newTokens[tenantId];
          return newTokens;
        });
      } else {
        // If tenantId not provided, find and remove token
        setVerificationTokens(prev => {
          const newTokens = { ...prev };
          const tenantIdToRemove = Object.keys(newTokens).find(key => newTokens[key] === token);
          if (tenantIdToRemove) {
            delete newTokens[tenantIdToRemove];
          }
          return newTokens;
        });
      }
    } catch (error: any) {
      console.error("Failed to verify email:", error);
      
      const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(error);
      
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMessage,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    }
  };

  const handleUpdateTenant = async () => {
    if (!selectedTenant || !updateFormData.tenant_id) return;
    
    if (!checkSessionExpiry()) return;

    setIsUpdating(true);
    try {
      const updatePayload: TenantUpdateRequest = {
        tenant_id: updateFormData.tenant_id,
      };

      // Only include fields that have been changed
      if (updateFormData.organization_name !== selectedTenant.organization_name) {
        updatePayload.organization_name = updateFormData.organization_name;
      }
      if (updateFormData.contact_email !== selectedTenant.email) {
        updatePayload.contact_email = updateFormData.contact_email;
      }
      if (updateFormData.domain !== selectedTenant.domain) {
        updatePayload.domain = updateFormData.domain;
      }
      // Use quota data from state instead of updateFormData
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
      const fetchedTenants = await listAdopterTenants();
      setTenants(fetchedTenants);
      
      setIsEditingTenant(false);
      onClose();
      setSelectedTenant(null);
      setUpdateFormData({});
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
      setIsUpdating(false);
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

  return (
    <>
      <Head>
        <title>Tenant Management - AI4Inclusion</title>
      </Head>
      <ContentLayout>
        <VStack spacing={6} align="stretch" w="full">
          <Heading size="lg" color="gray.700">
            Tenant Management
          </Heading>
          <Text color="gray.600" fontSize="sm">
            Manage your tenants as an Adopter Admin. View and update tenant information.
          </Text>

          <Tabs index={activeTab} onChange={setActiveTab} colorScheme="blue">
            <TabList>
              <Tab>List Tenants</Tab>
            </TabList>

            <TabPanels>
              <TabPanel px={0}>
                <Card bg={bgColor} borderColor={borderColor} borderWidth="1px">
                  <CardHeader>
                    <HStack justify="space-between" align="center">
                      <Heading size="md">Your Tenants</Heading>
                      <Button
                        colorScheme="green"
                        size="sm"
                        onClick={onCreateOpen}
                        leftIcon={<Text>+</Text>}
                      >
                        Create Tenant
                      </Button>
                    </HStack>
                  </CardHeader>
                  <CardBody>
                    {isLoading ? (
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
                                  <HStack spacing={2}>
                                    {tenant.status === "PENDING" && (
                                      <>
                                        <Button
                                          size="xs"
                                          colorScheme="orange"
                                          onClick={() => handleResendVerification(tenant.tenant_id)}
                                          isLoading={isResendingVerification === tenant.tenant_id}
                                          loadingText="Resending"
                                        >
                                          Resend Verification
                                        </Button>
                                        {verificationTokens[tenant.tenant_id] && (
                                          <Button
                                            size="xs"
                                            colorScheme="green"
                                            onClick={() => handleVerifyEmail(verificationTokens[tenant.tenant_id], tenant.tenant_id)}
                                          >
                                            Verify Now
                                          </Button>
                                        )}
                                      </>
                                    )}
                                    <Button
                                      size="xs"
                                      colorScheme="blue"
                                      onClick={() => handleEditTenant(tenant)}
                                    >
                                      Update
                                    </Button>
                                  </HStack>
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
            </TabPanels>
          </Tabs>
        </VStack>

        {/* Create Tenant Modal */}
        <Modal
          isOpen={isCreateOpen}
          onClose={onCreateClose}
          size="xl"
          initialFocusRef={createInitialRef}
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
                    ref={createInitialRef}
                    value={createFormData.organization_name || ""}
                    onChange={(e) =>
                      setCreateFormData({
                        ...createFormData,
                        organization_name: e.target.value,
                      })
                    }
                    placeholder="Enter organization name"
                  />
                </FormControl>

                <FormControl isRequired>
                  <FormLabel>Domain</FormLabel>
                  <Input
                    value={createFormData.domain || ""}
                    onChange={(e) =>
                      setCreateFormData({
                        ...createFormData,
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
                    value={createFormData.contact_email || ""}
                    onChange={(e) =>
                      setCreateFormData({
                        ...createFormData,
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
                isLoading={isCreating}
                loadingText="Creating"
              >
                Create Tenant
              </Button>
              <Button onClick={onCreateClose} isDisabled={isCreating}>
                Cancel
              </Button>
            </ModalFooter>
          </ModalContent>
        </Modal>

        {/* Update Tenant Modal */}
        <Modal
          isOpen={isOpen}
          onClose={() => {
            onClose();
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
          initialFocusRef={initialRef}
        >
          <ModalOverlay />
          <ModalContent>
            <ModalHeader>Update Tenant - Editable Quotas</ModalHeader>
            <ModalCloseButton />
            <ModalBody pb={6}>
              {selectedTenant && (
                <VStack spacing={4} align="stretch">
                  <FormControl>
                    <FormLabel>Tenant ID</FormLabel>
                    <Input
                      value={selectedTenant.tenant_id}
                      isReadOnly
                      bg="gray.50"
                      fontSize="sm"
                    />
                  </FormControl>

                  <FormControl>
                    <FormLabel>Organization Name</FormLabel>
                    <Input
                      ref={initialRef}
                      value={updateFormData.organization_name || ""}
                      onChange={(e) =>
                        setUpdateFormData({
                          ...updateFormData,
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
                      value={updateFormData.contact_email || ""}
                      onChange={(e) =>
                        setUpdateFormData({
                          ...updateFormData,
                          contact_email: e.target.value,
                        })
                      }
                      placeholder="Enter contact email"
                    />
                  </FormControl>

                  <FormControl>
                    <FormLabel>Domain</FormLabel>
                    <Input
                      value={updateFormData.domain || ""}
                      onChange={(e) =>
                        setUpdateFormData({
                          ...updateFormData,
                          domain: e.target.value,
                        })
                      }
                      placeholder="Enter domain"
                    />
                  </FormControl>

                  <FormControl>
                    <FormLabel>Requested Quotas (Editable)</FormLabel>
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
                    <FormLabel>Usage Quota (Editable)</FormLabel>
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
                isLoading={isUpdating}
                loadingText="Updating"
              >
                Update Tenant
              </Button>
              <Button onClick={onClose} isDisabled={isUpdating}>
                Cancel
              </Button>
            </ModalFooter>
          </ModalContent>
        </Modal>
      </ContentLayout>
    </>
  );
};

export default TenantManagementPage;
