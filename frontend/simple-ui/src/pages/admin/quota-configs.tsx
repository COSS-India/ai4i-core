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
  IconButton,
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
  Select,
} from "@chakra-ui/react";
import { CloseIcon } from "@chakra-ui/icons";
import Head from "next/head";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import ContentLayout from "../../components/common/ContentLayout";
import { useAuth } from "../../hooks/useAuth";
import {
  createQuotaConfig,
  deleteQuotaConfig,
  getQuotaConfigs,
  QuotaConfig,
  QuotaServiceLimitRow,
  updateQuotaConfig,
} from "../../services/quotaConfigService";
import type { Service } from "../../services/servicesManagementService";
import { listServices } from "../../services/servicesManagementService";
import { useToastWithDeduplication } from "../../hooks/useToastWithDeduplication";
import { extractErrorInfo } from "../../utils/errorHandler";

const BASE_SERVICE_TYPES = ["ASR", "NMT", "TTS", "LLM", "Transliteration", "Pipeline"];

const STATIC_UNIT_BY_TYPE: Record<string, string> = {
  ASR: "minutes",
  NMT: "characters",
  TTS: "characters",
  LLM: "tokens",
  Transliteration: "characters",
  TRANSLITERATION: "characters",
  PIPELINE: "units",
};

function normalizeTaskType(s: Service): string {
  const raw = (s.task_type || s.task?.type || s.name || "").toString().trim();
  if (!raw) return "";
  const up = raw.toUpperCase().replace(/\s+/g, "_");
  if (up.includes("ASR") || up === "SPEECH_TO_TEXT") return "ASR";
  if (up.includes("NMT") || up.includes("MT_") || up === "TRANSLATION") return "NMT";
  if (up.includes("TTS")) return "TTS";
  if (up.includes("LLM")) return "LLM";
  if (up.includes("TRANSLITER")) return "Transliteration";
  if (up.includes("PIPELINE")) return "Pipeline";
  return raw.charAt(0).toUpperCase() + raw.slice(1);
}

function buildServiceTypeOptions(services: Service[]): string[] {
  const fromApi = new Set<string>();
  for (const s of services) {
    const t = normalizeTaskType(s);
    if (t) fromApi.add(t);
  }
  return Array.from(new Set([...BASE_SERVICE_TYPES, ...Array.from(fromApi)])).sort((a, b) =>
    a.localeCompare(b)
  );
}

function unitTypeForSelection(serviceType: string, services: Service[]): string {
  const st = serviceType.trim();
  if (!st) return "";
  const key = st.toUpperCase().replace(/\s+/g, "_");
  if (STATIC_UNIT_BY_TYPE[st]) return STATIC_UNIT_BY_TYPE[st];
  if (STATIC_UNIT_BY_TYPE[key]) return STATIC_UNIT_BY_TYPE[key];
  for (const s of services) {
    if (normalizeTaskType(s) === st) {
      const u = (s.unit_type || s.billing_unit_type || "").toString();
      if (u) return u;
    }
  }
  return "units";
}

type LimitRow = { rowId: string; service_type: string; limit_value: string };

function newRowId(): string {
  return `r-${Math.random().toString(36).slice(2, 11)}`;
}

export default function QuotaConfigsAdminPage() {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const isAdmin = Boolean(user?.roles?.includes("ADMIN") || user?.is_superuser);
  const toast = useToastWithDeduplication();
  const { isOpen, onOpen, onClose } = useDisclosure();
  const [rows, setRows] = useState<QuotaConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [reqHourInput, setReqHourInput] = useState("1000");
  const [limitRows, setLimitRows] = useState<LimitRow[]>([{ rowId: newRowId(), service_type: "", limit_value: "" }]);
  const [saving, setSaving] = useState(false);
  const [catalogServices, setCatalogServices] = useState<Service[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(false);

  const serviceTypeOptions = useMemo(() => buildServiceTypeOptions(catalogServices), [catalogServices]);

  const resetCreateForm = useCallback(() => {
    setName("");
    setReqHourInput("1000");
    setLimitRows([{ rowId: newRowId(), service_type: "", limit_value: "" }]);
  }, []);

  const loadCatalog = useCallback(async () => {
    setCatalogLoading(true);
    try {
      setCatalogServices(await listServices());
    } catch {
      setCatalogServices([]);
    } finally {
      setCatalogLoading(false);
    }
  }, []);

  const openCreateModal = useCallback(() => {
    setEditingId(null);
    resetCreateForm();
    void loadCatalog();
    onOpen();
  }, [onOpen, resetCreateForm, loadCatalog]);

  const openEditModal = useCallback(
    (row: QuotaConfig) => {
      setEditingId(row.id);
      setName(row.name);
      setReqHourInput(String(row.requests_per_hour));
      const sl = row.service_limits || [];
      if (sl.length === 0) {
        setLimitRows([{ rowId: newRowId(), service_type: "", limit_value: "" }]);
      } else {
        setLimitRows(
          sl.map((x) => ({
            rowId: newRowId(),
            service_type: x.service_type,
            limit_value: String(x.limit_value),
          }))
        );
      }
      void loadCatalog();
      onOpen();
    },
    [onOpen, loadCatalog]
  );

  const closeCreateModal = useCallback(() => {
    setEditingId(null);
    resetCreateForm();
    onClose();
  }, [onClose, resetCreateForm]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await getQuotaConfigs());
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

  const selectedTypes = useMemo(
    () => new Set(limitRows.map((r) => r.service_type.trim()).filter(Boolean)),
    [limitRows]
  );

  const submit = async () => {
    const reqHour = parseInt(reqHourInput.trim(), 10);
    if (!name.trim()) {
      toast({ title: "Name required", status: "warning", isClosable: true });
      return;
    }
    if (reqHourInput.trim() === "" || Number.isNaN(reqHour) || reqHour < 0) {
      toast({ title: "Invalid request/hour", description: "Enter a non-negative whole number.", status: "warning", isClosable: true });
      return;
    }
    const service_limits: QuotaServiceLimitRow[] = [];
    for (const r of limitRows) {
      const st = r.service_type.trim();
      if (!st) continue;
      const lv = parseInt(r.limit_value.trim(), 10);
      if (r.limit_value.trim() === "" || Number.isNaN(lv) || lv < 0) {
        toast({ title: "Invalid limit", description: `Enter a limit for ${st}.`, status: "warning", isClosable: true });
        return;
      }
      service_limits.push({
        service_type: st,
        unit_type: unitTypeForSelection(st, catalogServices),
        limit_value: lv,
      });
    }
    setSaving(true);
    try {
      if (editingId) {
        await updateQuotaConfig(editingId, {
          name: name.trim(),
          requests_per_hour: reqHour,
          service_limits,
        });
        toast({ title: "Updated", status: "success", isClosable: true });
      } else {
        await createQuotaConfig({
          name: name.trim(),
          requests_per_hour: reqHour,
          service_limits,
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
        <title>Quota Configs - AI4I Platform</title>
      </Head>
      <ContentLayout>
        <Box maxW="7xl" mx="auto" py={8} px={4}>
          <HStack justify="space-between" mb={6}>
            <Heading size="lg">Quota configs</Heading>
            <Button colorScheme="blue" onClick={openCreateModal}>
              Add new
            </Button>
          </HStack>
          <Card>
            <CardHeader>
              <Text color="gray.600">Unique name per config; match plan and rate-limit names for auto-linking.</Text>
            </CardHeader>
            <CardBody>
              {loading ? (
                <Spinner />
              ) : (
                <Table size="sm" variant="simple">
                  <Thead>
                    <Tr>
                      <Th>Name</Th>
                      <Th>Req/hour</Th>
                      <Th>Service limits</Th>
                      <Th />
                    </Tr>
                  </Thead>
                  <Tbody>
                    {rows.map((r) => (
                      <Tr key={r.id}>
                        <Td>{r.name}</Td>
                        <Td>{r.requests_per_hour}</Td>
                        <Td>
                          <Text fontSize="xs" noOfLines={3}>
                            {(r.service_limits || [])
                              .map((x) => `${x.service_type}: ${x.limit_value.toLocaleString("en-IN")} ${x.unit_type}`)
                              .join(" · ")}
                          </Text>
                        </Td>
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
                                  await deleteQuotaConfig(r.id);
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

        <Modal isOpen={isOpen} onClose={closeCreateModal} size="xl">
          <ModalOverlay />
          <ModalContent>
            <ModalHeader>{editingId ? "Edit quota config" : "Create quota config"}</ModalHeader>
            <ModalCloseButton />
            <ModalBody>
              {catalogLoading && (
                <Text fontSize="sm" color="gray.600" mb={2}>
                  Loading service catalog…
                </Text>
              )}
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
                  <FormLabel>Request/hour</FormLabel>
                  <Input
                    type="text"
                    inputMode="numeric"
                    autoComplete="off"
                    placeholder="e.g. 1000"
                    value={reqHourInput}
                    onChange={(e) => setReqHourInput(e.target.value.replace(/\D/g, ""))}
                    bg="white"
                  />
                </FormControl>
                <Text fontWeight="semibold">Service limits</Text>
                <Table size="sm" variant="simple">
                  <Thead>
                    <Tr>
                      <Th>Service type</Th>
                      <Th>Unit</Th>
                      <Th>Limit</Th>
                      <Th w="48px" />
                    </Tr>
                  </Thead>
                  <Tbody>
                    {limitRows.map((lr, i) => {
                      const unit = lr.service_type ? unitTypeForSelection(lr.service_type, catalogServices) : "—";
                      return (
                        <Tr key={lr.rowId}>
                          <Td>
                            <Select
                              placeholder="Select service"
                              value={lr.service_type}
                              onChange={(e) => {
                                const v = e.target.value;
                                const next = [...limitRows];
                                next[i] = { ...next[i], service_type: v };
                                setLimitRows(next);
                              }}
                              bg="white"
                              size="sm"
                            >
                              {serviceTypeOptions.map((opt) => {
                                const takenElsewhere = selectedTypes.has(opt) && lr.service_type !== opt;
                                return (
                                  <option key={opt} value={opt} disabled={takenElsewhere}>
                                    {opt}
                                  </option>
                                );
                              })}
                            </Select>
                          </Td>
                          <Td>
                            <Text fontSize="sm">{unit}</Text>
                          </Td>
                          <Td>
                            <Input
                              placeholder="e.g. 10000"
                              size="sm"
                              value={lr.limit_value}
                              onChange={(e) => {
                                const next = [...limitRows];
                                next[i] = { ...next[i], limit_value: e.target.value.replace(/\D/g, "") };
                                setLimitRows(next);
                              }}
                              bg="white"
                            />
                          </Td>
                          <Td>
                            <IconButton
                              aria-label="Remove row"
                              icon={<CloseIcon />}
                              size="sm"
                              variant="ghost"
                              onClick={() => {
                                if (limitRows.length <= 1) {
                                  setLimitRows([{ rowId: newRowId(), service_type: "", limit_value: "" }]);
                                } else {
                                  setLimitRows(limitRows.filter((_, j) => j !== i));
                                }
                              }}
                            />
                          </Td>
                        </Tr>
                      );
                    })}
                  </Tbody>
                </Table>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setLimitRows([...limitRows, { rowId: newRowId(), service_type: "", limit_value: "" }])}
                >
                  + Add service
                </Button>
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
