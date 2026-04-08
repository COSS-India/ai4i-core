import {
  Badge,
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
  Select,
  SimpleGrid,
  Spinner,
  Table,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
  useColorModeValue,
  useDisclosure,
  VStack,
} from "@chakra-ui/react";
import Head from "next/head";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/router";
import ContentLayout from "../../components/common/ContentLayout";
import { useAuth } from "../../hooks/useAuth";
import {
  createPolicy,
  deletePolicy,
  getPolicies,
  PlanPolicy,
  updatePolicy,
} from "../../services/policyService";
import { getQuotaConfigByName } from "../../services/quotaConfigService";
import { getRateLimitConfigByName } from "../../services/rateLimitConfigService";
import { useToastWithDeduplication } from "../../hooks/useToastWithDeduplication";
import {
  getPricingSummary,
  type PricingSummaryRow,
} from "../../services/pricingSummaryService";
import { extractErrorInfo } from "../../utils/errorHandler";
import {
  formatQuotaSummary,
  formatRateSummary,
  groupPoliciesByName,
  tierModelsLabel,
} from "../../utils/planGrouping";

const TIERS = ["Tier-1", "Tier-2", "Tier-3"];

function unitTypeDisplayLabel(unit: string): string {
  const u = (unit || "").toLowerCase();
  if (u === "minutes" || u === "minute") return "per minute of audio";
  if (u.includes("char")) return "per 1,000 characters";
  if (u.includes("token")) return "per 1,000 tokens";
  if (u === "requests" || u === "request" || u === "units") return "per unit";
  return unit || "—";
}

function servicePriorityBadge(taskType: string): "P1" | "P2" {
  const t = taskType.toUpperCase();
  if (t === "ASR" || t === "NMT" || t === "LLM") return "P1";
  return "P2";
}

function planGroupSortOrder(name: string): number {
  const n = name.toLowerCase();
  const order = ["basic", "standard", "premium", "economy", "balanced"];
  const i = order.indexOf(n);
  return i === -1 ? 50 : i;
}

export default function PoliciesAdminPage() {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const isAdmin = Boolean(user?.roles?.includes("ADMIN") || user?.is_superuser);
  const toast = useToastWithDeduplication();
  const { isOpen, onOpen, onClose } = useDisclosure();
  const [rows, setRows] = useState<PlanPolicy[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingPlan, setEditingPlan] = useState<PlanPolicy | null>(null);
  const [planName, setPlanName] = useState("");
  const [planCost, setPlanCost] = useState("100");
  const [tier, setTier] = useState("Tier-2");
  const [previewQ, setPreviewQ] = useState<string | null>(null);
  const [previewR, setPreviewR] = useState<string | null>(null);
  const [previewQLoading, setPreviewQLoading] = useState(false);
  const [previewRLoading, setPreviewRLoading] = useState(false);
  const [quotaFound, setQuotaFound] = useState(false);
  const [rateFound, setRateFound] = useState(false);
  const [tierError, setTierError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [pricingRows, setPricingRows] = useState<PricingSummaryRow[]>([]);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "whiteAlpha.300");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [policiesResult, pricingResult] = await Promise.allSettled([
        getPolicies(),
        getPricingSummary(),
      ]);
      if (policiesResult.status === "fulfilled") {
        setRows(policiesResult.value);
      } else {
        const { message } = extractErrorInfo(policiesResult.reason);
        toast({ title: "Plans load failed", description: message, status: "error", isClosable: true });
        setRows([]);
      }
      if (pricingResult.status === "fulfilled") {
        setPricingRows(pricingResult.value);
      } else {
        const { message } = extractErrorInfo(pricingResult.reason);
        toast({ title: "Pricing summary failed", description: message, status: "warning", isClosable: true });
        setPricingRows([]);
      }
    } finally {
      setLoading(false);
    }
  }, [toast]);

  const planGroupsSorted = useMemo(() => {
    return [...groupPoliciesByName(rows)].sort(
      (a, b) => planGroupSortOrder(a.name) - planGroupSortOrder(b.name) || a.name.localeCompare(b.name)
    );
  }, [rows]);

  const runPreviewFetch = useCallback(async (name: string) => {
    const n = name.trim();
    if (!n) {
      setPreviewQ(null);
      setPreviewR(null);
      setQuotaFound(false);
      setRateFound(false);
      return;
    }
    setPreviewQLoading(true);
    setPreviewRLoading(true);
    setQuotaFound(false);
    setRateFound(false);
    try {
      const [q, r] = await Promise.all([
        getQuotaConfigByName(n).then(
          (d) => {
            setQuotaFound(true);
            return d;
          },
          () => {
            setQuotaFound(false);
            return null;
          }
        ),
        getRateLimitConfigByName(n).then(
          (d) => {
            setRateFound(true);
            return d;
          },
          () => {
            setRateFound(false);
            return null;
          }
        ),
      ]);
      if (q) {
        const sl = (q as { service_limits?: unknown[] }).service_limits || [];
        const lines = [`Request/hour: ${(q as { requests_per_hour?: number }).requests_per_hour ?? "—"}`];
        if (Array.isArray(sl)) {
          for (const row of sl) {
            const o = row as { service_type?: string; limit_value?: number; unit_type?: string };
            if (o.service_type != null) {
              lines.push(`${o.service_type}: ${(o.limit_value ?? 0).toLocaleString()} ${o.unit_type || ""}`.trim());
            }
          }
        }
        setPreviewQ(lines.join("\n"));
      } else {
        setPreviewQ(null);
      }
      if (r) {
        setPreviewR(
          `Per API key: ${(r as { requests_per_hour_per_api_key?: number }).requests_per_hour_per_api_key ?? "—"} req/hour\nPer tenant: ${(r as { requests_per_hour_per_tenant?: number }).requests_per_hour_per_tenant ?? "—"} req/hour`
        );
      } else {
        setPreviewR(null);
      }
    } finally {
      setPreviewQLoading(false);
      setPreviewRLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      void runPreviewFetch(planName);
    }, 500);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [planName, isOpen, runPreviewFetch]);

  useEffect(() => {
    if (!isOpen || !tier) {
      setTierError(null);
      return;
    }
    const taken = rows.some((p) => p.tier === tier && (!editingPlan || p.id !== editingPlan.id));
    setTierError(taken ? "This tier is already assigned to another plan." : null);
  }, [tier, rows, isOpen, editingPlan]);

  useEffect(() => {
    if (!authLoading && (!isAuthenticated || !isAdmin)) router.push("/");
  }, [authLoading, isAuthenticated, isAdmin, router]);

  useEffect(() => {
    if (isAdmin && isAuthenticated) void load();
  }, [isAdmin, isAuthenticated, load]);

  const openCreate = () => {
    setEditingPlan(null);
    setPlanName("");
    setPlanCost("100");
    setTier("Tier-2");
    setPreviewQ(null);
    setPreviewR(null);
    onOpen();
  };

  const openEdit = (p: PlanPolicy) => {
    setEditingPlan(p);
    setPlanName(p.plan_name);
    setPlanCost(String(p.cost ?? 100));
    setTier(p.tier);
    void runPreviewFetch(p.plan_name);
    onOpen();
  };

  const closeModal = () => {
    setEditingPlan(null);
    onClose();
  };

  const canSave =
    planName.trim() &&
    quotaFound &&
    rateFound &&
    !tierError &&
    !Number.isNaN(Number(planCost)) &&
    Number(planCost) >= 0;

  const submit = async () => {
    if (!canSave) return;
    setSaving(true);
    try {
      const costNum = Number(planCost);
      if (editingPlan) {
        await updatePolicy(editingPlan.id, { plan_name: planName.trim(), cost: costNum, tier });
        toast({ title: "Plan updated", status: "success", isClosable: true });
      } else {
        await createPolicy({ plan_name: planName.trim(), cost: costNum, tier });
        toast({ title: "Plan created", status: "success", isClosable: true });
      }
      closeModal();
      await load();
    } catch (e: unknown) {
      const { message } = extractErrorInfo(e);
      toast({ title: "Save failed", description: message, status: "error", isClosable: true });
    } finally {
      setSaving(false);
    }
  };

  const removePlan = async (p: PlanPolicy) => {
    try {
      await deletePolicy(p.id);
      toast({ title: "Plan removed", status: "success", isClosable: true });
      await load();
    } catch (e: unknown) {
      const { message } = extractErrorInfo(e);
      toast({ title: "Delete failed", description: message, status: "error", isClosable: true });
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
        <title>Pricing & plans - AI4I Platform</title>
      </Head>
      <ContentLayout>
        <Box maxW="7xl" mx="auto" py={8} px={4}>
          <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px">
            <CardHeader pb={2}>
              <HStack justify="space-between" align="flex-start" flexWrap="wrap" gap={3}>
                <Box textAlign="left">
                  <Heading size="lg" color="gray.800">
                    Pricing configuration
                  </Heading>
                  <Text fontSize="sm" color="gray.600" mt={1} maxW="3xl">
                    Service costs are read from registered services (Tier-1 and Tier-2) linked to models by task
                    type. Plan quotas and rate limits come from the policy engine.
                  </Text>
                </Box>
                <Button colorScheme="blue" onClick={openCreate} flexShrink={0}>
                  Add plan
                </Button>
              </HStack>
            </CardHeader>
            <CardBody pt={0}>
              {loading ? (
                <Box py={10} textAlign="center">
                  <Spinner size="lg" color="orange.500" />
                </Box>
              ) : (
                <>
                  <Heading as="h2" size="sm" fontWeight="semibold" mb={3} color="gray.800">
                    Service pricing configuration
                  </Heading>
                  {pricingRows.length === 0 ? (
                    <Text fontSize="sm" color="gray.600" mb={8}>
                      No Tier-1 / Tier-2 services found. Register services with tier and cost in Services
                      Management.
                    </Text>
                  ) : (
                    <Box overflowX="auto" mb={10}>
                      <Table variant="simple" size="sm" minW="640px">
                        <Thead>
                          <Tr>
                            <Th>Service</Th>
                            <Th>Unit type</Th>
                            <Th isNumeric>Tier 1 (₹)</Th>
                            <Th isNumeric>Tier 2 (₹)</Th>
                            <Th>Priority</Th>
                          </Tr>
                        </Thead>
                        <Tbody>
                          {pricingRows.map((row) => {
                            const pr = servicePriorityBadge(row.task_type);
                            return (
                              <Tr key={row.task_type}>
                                <Td fontWeight="medium">{row.task_type}</Td>
                                <Td fontSize="sm" color="gray.700">
                                  {unitTypeDisplayLabel(row.unit_type)}
                                </Td>
                                <Td isNumeric>
                                  {row.tier_1 != null ? `₹${Number(row.tier_1.cost_per_unit).toFixed(2)}` : "—"}
                                </Td>
                                <Td isNumeric>
                                  {row.tier_2 != null ? `₹${Number(row.tier_2.cost_per_unit).toFixed(2)}` : "—"}
                                </Td>
                                <Td>
                                  <Badge colorScheme={pr === "P1" ? "red" : "orange"} fontSize="0.7rem">
                                    {pr}
                                  </Badge>
                                </Td>
                              </Tr>
                            );
                          })}
                        </Tbody>
                      </Table>
                    </Box>
                  )}

                  <Heading as="h2" size="sm" fontWeight="semibold" mb={3} color="gray.800">
                    Tier plan definitions
                  </Heading>
                  {planGroupsSorted.length === 0 ? (
                    <Text fontSize="sm" color="gray.600">
                      No plans yet. Use <strong>Add plan</strong> above to create Economy, Balanced, or Premium.
                    </Text>
                  ) : (
                    <SimpleGrid columns={{ base: 1, md: 3 }} spacing={4}>
                      {planGroupsSorted.map((g) => {
                        const popular = g.name.toLowerCase() === "standard";
                        return (
                          <Card
                            key={g.name}
                            variant="outline"
                            borderWidth={2}
                            position="relative"
                            borderColor={popular ? "blue.200" : cardBorder}
                          >
                            {popular && (
                              <Badge colorScheme="blue" position="absolute" top={2} right={2} fontSize="0.65rem">
                                Popular
                              </Badge>
                            )}
                            <CardHeader pb={2}>
                              <Heading size="md">{g.name}</Heading>
                            </CardHeader>
                            <CardBody pt={0}>
                              <VStack align="stretch" spacing={3}>
                                {g.policies.map((p) => (
                                  <Box key={p.id}>
                                    <Text fontSize="sm" fontWeight="semibold" color="gray.700" mb={2}>
                                      {tierModelsLabel(p.tier)}
                                    </Text>
                                    <Text fontSize="xs">Budget: ₹{Number(p.cost).toFixed(2)}</Text>
                                    <Text fontSize="xs" color="gray.700" mt={1}>
                                      <strong>Quota:</strong> {formatQuotaSummary(p)}
                                    </Text>
                                    <Text fontSize="xs" color="gray.700" mt={1}>
                                      <strong>Rate limits:</strong> {formatRateSummary(p)}
                                    </Text>
                                    <HStack mt={3} spacing={2}>
                                      <Button size="xs" variant="outline" onClick={() => openEdit(p)}>
                                        Edit
                                      </Button>
                                      <Button
                                        size="xs"
                                        variant="outline"
                                        colorScheme="red"
                                        onClick={() => void removePlan(p)}
                                      >
                                        Delete
                                      </Button>
                                    </HStack>
                                  </Box>
                                ))}
                              </VStack>
                            </CardBody>
                          </Card>
                        );
                      })}
                    </SimpleGrid>
                  )}
                </>
              )}
            </CardBody>
          </Card>
        </Box>

        <Modal isOpen={isOpen} onClose={closeModal} size="xl">
          <ModalOverlay />
          <ModalContent>
            <ModalHeader>{editingPlan ? "Edit plan" : "Create plan"}</ModalHeader>
            <ModalCloseButton />
            <ModalBody>
              <VStack spacing={4} align="stretch">
                <FormControl isRequired>
                  <FormLabel>Plan name</FormLabel>
                  <Input
                    placeholder="e.g. Economy, Balanced, Premium"
                    value={planName}
                    onChange={(e) => setPlanName(e.target.value)}
                    bg="white"
                  />
                </FormControl>
                <FormControl isRequired>
                  <FormLabel>Plan budget (₹)</FormLabel>
                  <Input
                    type="number"
                    min={0}
                    value={planCost}
                    onChange={(e) => setPlanCost(e.target.value)}
                    bg="white"
                  />
                </FormControl>
                <FormControl isRequired>
                  <FormLabel>Tier selection</FormLabel>
                  <Select value={tier} onChange={(e) => setTier(e.target.value)} bg="white">
                    {TIERS.map((t) => (
                      <option key={t} value={t}>
                        {tierModelsLabel(t)}
                      </option>
                    ))}
                  </Select>
                  {tierError && (
                    <Text fontSize="sm" color="red.500" mt={1}>
                      {tierError}
                    </Text>
                  )}
                </FormControl>
                <Box>
                  <Text fontWeight="semibold" mb={1}>
                    Quota config (auto)
                  </Text>
                  <Box p={3} bg="gray.50" borderRadius="md" minH="80px">
                    {previewQLoading ? (
                      <Spinner size="sm" />
                    ) : quotaFound && previewQ ? (
                      <Text fontSize="sm" whiteSpace="pre-wrap">
                        Quota: {planName.trim() || "—"}
                        {"\n"}
                        {previewQ}
                      </Text>
                    ) : planName.trim() ? (
                      <Text fontSize="sm" color="orange.600">
                        ⚠ No quota config found named &quot;{planName.trim()}&quot;. Create one first.
                      </Text>
                    ) : (
                      <Text fontSize="sm" color="gray.600">
                        Enter a plan name to match quota config.
                      </Text>
                    )}
                  </Box>
                </Box>
                <Box>
                  <Text fontWeight="semibold" mb={1}>
                    Rate limit (auto)
                  </Text>
                  <Box p={3} bg="gray.50" borderRadius="md" minH="80px">
                    {previewRLoading ? (
                      <Spinner size="sm" />
                    ) : rateFound && previewR ? (
                      <Text fontSize="sm" whiteSpace="pre-wrap">
                        Rate limit: {planName.trim() || "—"}
                        {"\n"}
                        {previewR}
                      </Text>
                    ) : planName.trim() ? (
                      <Text fontSize="sm" color="orange.600">
                        ⚠ No rate limit config found named &quot;{planName.trim()}&quot;. Create one first.
                      </Text>
                    ) : (
                      <Text fontSize="sm" color="gray.600">
                        Enter a plan name to match rate limit config.
                      </Text>
                    )}
                  </Box>
                </Box>
              </VStack>
            </ModalBody>
            <ModalFooter>
              <Button variant="ghost" mr={3} onClick={closeModal}>
                Cancel
              </Button>
              <Button colorScheme="blue" onClick={() => void submit()} isLoading={saving} isDisabled={!canSave}>
                Save plan
              </Button>
            </ModalFooter>
          </ModalContent>
        </Modal>
      </ContentLayout>
    </>
  );
}
