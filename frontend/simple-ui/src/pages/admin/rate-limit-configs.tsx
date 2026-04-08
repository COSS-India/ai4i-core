import {
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Center,
  FormControl,
  FormLabel,
  Heading,
  HStack,
  Input,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalOverlay,
  Spinner,
  Table,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
  useDisclosure,
  VStack,
} from "@chakra-ui/react";
import Head from "next/head";
import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/router";
import ContentLayout from "../../components/common/ContentLayout";
import { useAuth } from "../../hooks/useAuth";
import {
  createRateLimitConfig,
  deleteRateLimitConfig,
  getRateLimitConfigs,
  RateLimitConfig,
  updateRateLimitConfig,
} from "../../services/rateLimitConfigService";
import { useToastWithDeduplication } from "../../hooks/useToastWithDeduplication";
import { extractErrorInfo } from "../../utils/errorHandler";

export default function RateLimitConfigsAdminPage() {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const isAdmin = Boolean(user?.roles?.includes("ADMIN") || user?.is_superuser);
  const toast = useToastWithDeduplication();
  const { isOpen, onOpen, onClose } = useDisclosure();
  const [rows, setRows] = useState<RateLimitConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [rphKeyInput, setRphKeyInput] = useState("200");
  const [rphTenantInput, setRphTenantInput] = useState("1000");
  const [saving, setSaving] = useState(false);

  const resetCreateForm = useCallback(() => {
    setName("");
    setRphKeyInput("200");
    setRphTenantInput("1000");
  }, []);

  const openCreateModal = useCallback(() => {
    setEditingId(null);
    resetCreateForm();
    onOpen();
  }, [onOpen, resetCreateForm]);

  const openEditModal = useCallback(
    (row: RateLimitConfig) => {
      setEditingId(row.id);
      setName(row.name);
      setRphKeyInput(String(row.requests_per_hour_per_api_key));
      setRphTenantInput(String(row.requests_per_hour_per_tenant));
      onOpen();
    },
    [onOpen]
  );

  const closeCreateModal = useCallback(() => {
    setEditingId(null);
    resetCreateForm();
    onClose();
  }, [onClose, resetCreateForm]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await getRateLimitConfigs());
    } catch (e: unknown) {
      const { message } = extractErrorInfo(e);
      toast({ title: "Load failed", description: message, status: "error", isClosable: true });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    if (!authLoading && (!isAuthenticated || !isAdmin)) router.push("/");
  }, [authLoading, isAuthenticated, isAdmin, router]);

  useEffect(() => {
    if (isAdmin && isAuthenticated) void load();
  }, [isAdmin, isAuthenticated, load]);

  const submit = async () => {
    const rphKey = parseInt(rphKeyInput.trim(), 10);
    const rphTenant = parseInt(rphTenantInput.trim(), 10);
    if (!name.trim()) {
      toast({ title: "Name required", status: "warning", isClosable: true });
      return;
    }
    if (rphKeyInput.trim() === "" || Number.isNaN(rphKey) || rphKey < 0) {
      toast({ title: "Invalid rate", description: "Enter a non-negative whole number for API key.", status: "warning", isClosable: true });
      return;
    }
    if (rphTenantInput.trim() === "" || Number.isNaN(rphTenant) || rphTenant < 0) {
      toast({ title: "Invalid rate", description: "Enter a non-negative whole number for tenant.", status: "warning", isClosable: true });
      return;
    }
    setSaving(true);
    try {
      if (editingId) {
        await updateRateLimitConfig(editingId, {
          name: name.trim(),
          requests_per_hour_per_api_key: rphKey,
          requests_per_hour_per_tenant: rphTenant,
        });
        toast({ title: "Updated", status: "success", isClosable: true });
      } else {
        await createRateLimitConfig({
          name: name.trim(),
          requests_per_hour_per_api_key: rphKey,
          requests_per_hour_per_tenant: rphTenant,
        });
        toast({ title: "Saved", status: "success", isClosable: true });
      }
      closeCreateModal();
      await load();
    } catch (e: unknown) {
      const { message } = extractErrorInfo(e);
      toast({ title: "Save failed", description: message, status: "error", isClosable: true });
    } finally {
      setSaving(false);
    }
  };

  if (authLoading || !isAuthenticated || !isAdmin) {
    return (
      <ContentLayout>
        <Center h="400px">
          <Spinner size="xl" color="orange.500" />
        </Center>
      </ContentLayout>
    );
  }

  return (
    <>
      <Head>
        <title>Rate limit configs - AI4I Platform</title>
      </Head>
      <ContentLayout>
        <Box maxW="7xl" mx="auto" py={8} px={4}>
          <HStack justify="space-between" mb={6}>
            <Heading size="lg">Rate limit configs</Heading>
            <Button colorScheme="blue" onClick={openCreateModal}>
              Add new
            </Button>
          </HStack>
          <Card>
            <CardHeader>
              <Text color="gray.600">Name must match the plan and quota config name (e.g. Economy, Balanced, Premium).</Text>
            </CardHeader>
            <CardBody>
              {loading ? (
                <Spinner />
              ) : (
                <Table size="sm" variant="simple">
                  <Thead>
                    <Tr>
                      <Th>Name</Th>
                      <Th>Req/hour (API key)</Th>
                      <Th>Req/hour (tenant)</Th>
                      <Th />
                    </Tr>
                  </Thead>
                  <Tbody>
                    {rows.map((r) => (
                      <Tr key={r.id}>
                        <Td>{r.name}</Td>
                        <Td>{r.requests_per_hour_per_api_key}</Td>
                        <Td>{r.requests_per_hour_per_tenant}</Td>
                        <Td>
                          <HStack spacing={1}>
                            <Button size="xs" variant="outline" onClick={() => openEditModal(r)}>
                              Edit
                            </Button>
                            <Button
                              size="xs"
                              variant="outline"
                              colorScheme="red"
                              onClick={async () => {
                                try {
                                  await deleteRateLimitConfig(r.id);
                                  await load();
                                } catch (e: unknown) {
                                  const { message } = extractErrorInfo(e);
                                  toast({ title: "Delete failed", description: message, status: "error" });
                                }
                              }}
                            >
                              Delete
                            </Button>
                          </HStack>
                        </Td>
                      </Tr>
                    ))}
                  </Tbody>
                </Table>
              )}
            </CardBody>
          </Card>
        </Box>

        <Modal isOpen={isOpen} onClose={closeCreateModal}>
          <ModalOverlay />
          <ModalContent>
            <ModalHeader>{editingId ? "Edit rate limit config" : "Create rate limit config"}</ModalHeader>
            <ModalCloseButton />
            <ModalBody>
              <VStack spacing={4} align="stretch">
                <FormControl isRequired>
                  <FormLabel>Name</FormLabel>
                  <Input
                    placeholder="e.g. Economy, Balanced, Premium"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    bg="white"
                  />
                </FormControl>
                <FormControl isRequired>
                  <FormLabel>Request/hour per API key</FormLabel>
                  <Input
                    type="text"
                    inputMode="numeric"
                    autoComplete="off"
                    placeholder="e.g. 200"
                    value={rphKeyInput}
                    onChange={(e) => setRphKeyInput(e.target.value.replace(/\D/g, ""))}
                    bg="white"
                  />
                </FormControl>
                <FormControl isRequired>
                  <FormLabel>Request/hour per tenant</FormLabel>
                  <Input
                    type="text"
                    inputMode="numeric"
                    autoComplete="off"
                    placeholder="e.g. 1000"
                    value={rphTenantInput}
                    onChange={(e) => setRphTenantInput(e.target.value.replace(/\D/g, ""))}
                    bg="white"
                  />
                </FormControl>
              </VStack>
            </ModalBody>
            <ModalFooter>
              <Button variant="ghost" mr={3} onClick={closeCreateModal}>
                Cancel
              </Button>
              <Button colorScheme="blue" onClick={() => void submit()} isLoading={saving}>
                Save
              </Button>
            </ModalFooter>
          </ModalContent>
        </Modal>
      </ContentLayout>
    </>
  );
}
