// Traces Dashboard - User-friendly trace visualization

import {
  Box,
  Button,
  FormControl,
  FormLabel,
  Heading,
  HStack,
  Input,
  Text,
  VStack,
  Badge,
  Spinner,
  Flex,
  useColorModeValue,
  Card,
  CardBody,
  Grid,
  GridItem,
  Alert,
  AlertIcon,
  AlertDescription,
  Divider,
  Icon,
  Collapse,
} from "@chakra-ui/react";
import Head from "next/head";
import React, { useState, useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { SearchIcon, CheckCircleIcon } from "@chakra-ui/icons";
import { FiClock, FiGlobe, FiSettings, FiEye, FiEyeOff, FiInfo, FiLayers } from "react-icons/fi";
import ContentLayout from "../components/common/ContentLayout";
import ManagementPageHeader from "../components/common/ManagementPageHeader";
import { useAuth } from "../hooks/useAuth";
import { useRouter } from "next/router";
import {
  getTraceById,
  Trace,
  Span,
} from "../services/observabilityService";
import { showToast } from "../utils/toast";
import { getPlatformName } from "../config/runtimeConfig";
import {
  extractImportantSpans,
  formatDuration,
  formatRelativeTime,
  formatTagValue,
  formatTimestamp,
  getTraceStatus,
  getUserFriendlyDescription,
  parseErrorDetails,
  type ProcessedSpan,
} from "../components/traces/traceSpanPresentation";

const TracesPage: React.FC = () => {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading, user } = useAuth();
  const [traceIdSearch, setTraceIdSearch] = useState<string>("");
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
  const [expandedTags, setExpandedTags] = useState<Set<string>>(new Set());

  const cardBg = useColorModeValue("white", "gray.800");
  const borderColor = useColorModeValue("gray.200", "gray.700");
  const bgGradient = useColorModeValue("linear(to-br, blue.50, purple.50)", "linear(to-br, gray.900, gray.800)");

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      showToast({
        type: "warning",
        message: "Please log in to view traces.",
      });
      router.push("/auth");
    }
  }, [isAuthenticated, authLoading, router]);

  // Handle traceId from query parameter (e.g., from logs page)
  useEffect(() => {
    if (router.isReady && router.query.traceId) {
      const traceIdFromQuery = String(router.query.traceId).trim();
      if (traceIdFromQuery) {
        setTraceIdSearch(traceIdFromQuery);
        setSelectedTraceId(traceIdFromQuery);
      }
    }
  }, [router.isReady, router.query.traceId]);

  // Fetch selected trace details (only if authenticated and ADMIN)
  const { data: traceDetails, isLoading: traceDetailsLoading, error: traceError } = useQuery({
    queryKey: ["trace-details", selectedTraceId],
    queryFn: () => getTraceById(selectedTraceId!),
    enabled: !!selectedTraceId && isAuthenticated,
    staleTime: 5 * 60 * 1000,
  });

  const handleSearchByTraceId = async () => {
    if (!traceIdSearch.trim()) {
      showToast({
        type: "warning",
        message: "Please enter a trace ID to search.",
      });
      return;
    }

    try {
      setSelectedTraceId(traceIdSearch.trim());
    } catch (error: any) {
      showToast({
        type: "error",
        message: error?.message || "Could not find trace with the provided ID.",
      });
    }
  };

  // Process trace data
  const processedSpans = useMemo(() => {
    if (!traceDetails) {
      console.log("No trace details available");
      return [];
    }

    try {
      console.log("Processing trace:", {
        traceID: traceDetails.traceID,
        spansCount: traceDetails.spans?.length || 0,
        processesCount: traceDetails.processes ? Object.keys(traceDetails.processes).length : 0,
        startTime: traceDetails.startTime,
        duration: traceDetails.duration,
        hasSpans: !!traceDetails.spans,
        hasProcesses: !!traceDetails.processes,
      });

      if (!traceDetails.spans || traceDetails.spans.length === 0) {
        console.warn("Trace has no spans!");
        return [];
      }

      if (!traceDetails.processes || Object.keys(traceDetails.processes).length === 0) {
        console.warn("Trace has no processes!");
        return [];
      }

      if (!traceDetails.startTime) {
        console.warn("Trace has no startTime!");
        // Try to calculate from spans
        const minStartTime = Math.min(...traceDetails.spans.map((s: Span) => s.startTime));
        if (minStartTime) {
          console.log("Using min span startTime as trace startTime:", minStartTime);
          traceDetails.startTime = minStartTime;
        } else {
          return [];
        }
      }

      const spans = extractImportantSpans(traceDetails);
      console.log("Extracted", spans.length, "important spans");

      // Debug logging
      if (spans.length === 0 && traceDetails.spans && traceDetails.spans.length > 0) {
        console.warn("No spans extracted from trace. Total spans:", traceDetails.spans.length);
        console.log("Sample span operations:", traceDetails.spans.slice(0, 10).map((s: Span) => ({
          op: s.operationName,
          duration: s.duration,
          startTime: s.startTime,
          processID: s.processID,
          service: traceDetails.processes?.[s.processID]?.serviceName || "unknown",
          tags: s.tags?.slice(0, 3).map(t => `${t.key}:${t.value}`) || []
        })));
      }
      return spans;
    } catch (error) {
      console.error("Error processing spans:", error);
      console.error("Trace details:", traceDetails);
      return [];
    }
  }, [traceDetails]);

  const traceStatus = useMemo(() => {
    if (!traceDetails) return { status: "success" as const, message: "Completed" };
    return getTraceStatus(traceDetails);
  }, [traceDetails]);

  // Build span map and parent-child relationships for tag merging
  const spanRelationships = useMemo(() => {
    if (!traceDetails || !traceDetails.spans) {
      return {
        spanMap: new Map<string, Span>(),
        spanToParent: new Map<string, string>(),
        childSpans: new Map<string, string[]>()
      };
    }

    const spanMap = new Map<string, Span>();
    const spanToParent = new Map<string, string>();
    const childSpans = new Map<string, string[]>(); // parentSpanID -> [childSpanIDs]

    traceDetails.spans.forEach((span: Span) => {
      spanMap.set(span.spanID, span);

      if (span.references && span.references.length > 0) {
        const parentRef = span.references.find(ref => ref.refType === "CHILD_OF");
        if (parentRef) {
          spanToParent.set(span.spanID, parentRef.spanID);
          // Build child spans map
          if (!childSpans.has(parentRef.spanID)) {
            childSpans.set(parentRef.spanID, []);
          }
          childSpans.get(parentRef.spanID)!.push(span.spanID);
        }
      }
    });

    return { spanMap, spanToParent, childSpans };
  }, [traceDetails]);

  // Extract primary error message from the most descriptive failed span
  const primaryErrorMessage = useMemo(() => {
    if (!processedSpans || processedSpans.length === 0) return null;

    // Helper function to check if an error message is trivial/not useful
    const isTrivialError = (msg: string | undefined): boolean => {
      if (!msg) return true;
      const msgLower = msg.toLowerCase().trim();
      // Filter out boolean values, single characters, very short messages, or generic status codes
      return msgLower === "true" ||
             msgLower === "false" ||
             msgLower.length <= 3 ||
             msgLower === "error" ||
             /^status:\s*\d+$/.test(msgLower) ||
             /^\d+$/.test(msgLower);
    };

    // Collect all error messages with their spans
    const errorSpans = processedSpans
      .filter((p: ProcessedSpan) => p.hasError && p.errorMessage && !isTrivialError(p.errorMessage))
      .map((p: ProcessedSpan) => ({
        span: p,
        errorMessage: p.errorMessage!,
        priority: 0, // Higher priority = better
      }));

    // If we have non-trivial errors, prioritize them
    if (errorSpans.length > 0) {
      // Prioritize error messages:
      // 1. Reject operations (most specific)
      // 2. Longer, more descriptive messages
      // 3. Messages from top-level spans
      errorSpans.forEach((item: { span: ProcessedSpan; errorMessage: string; priority: number }) => {
        if (item.span.category === "error" || item.span.displayName.includes("Rejection")) {
          item.priority += 10; // Highest priority for rejections
        }
        if (item.span.isTopLevel) {
          item.priority += 5; // Higher priority for top-level spans
        }
        if (item.errorMessage.length > 20) {
          item.priority += 3; // Prefer longer, more descriptive messages
        }
        if (item.errorMessage.length > 10) {
          item.priority += 1; // Slight boost for medium-length messages
        }
      });

      // Sort by priority (descending) and return the best one
      errorSpans.sort((a: { span: ProcessedSpan; errorMessage: string; priority: number }, b: { span: ProcessedSpan; errorMessage: string; priority: number }) => b.priority - a.priority);
      return errorSpans[0]?.errorMessage || null;
    }

    // Fallback: if all errors are trivial, try to find any error message
    // But still prefer rejection operations
    const anyError = processedSpans.find((p: ProcessedSpan) =>
      p.hasError && p.errorMessage && (p.category === "error" || p.displayName.includes("Rejection"))
    );
    if (anyError && anyError.errorMessage) {
      return anyError.errorMessage;
    }

    // Last resort: return first error message even if trivial
    const firstError = processedSpans.find((p: ProcessedSpan) => p.hasError && p.errorMessage);
    return firstError?.errorMessage || null;
  }, [processedSpans]);

  // Calculate trace startTime and duration from spans if not provided
  const traceStartTime = useMemo(() => {
    if (!traceDetails || !traceDetails.spans || traceDetails.spans.length === 0) {
      return traceDetails?.startTime;
    }

    // If startTime is already provided and valid, use it
    if (traceDetails.startTime && traceDetails.startTime > 0) {
      return traceDetails.startTime;
    }

    // Otherwise, calculate from spans: find the earliest start
    const spans = traceDetails.spans;
    const startTimes = spans.map((s: Span) => s.startTime).filter((t: number) => t > 0);

    if (startTimes.length > 0) {
      const earliestStart = Math.min(...startTimes);
      console.log("Calculated trace startTime from spans:", earliestStart);
      return earliestStart;
    }

    return traceDetails.startTime;
  }, [traceDetails]);

  // Calculate trace duration from spans if not provided
  const traceDuration = useMemo(() => {
    if (!traceDetails || !traceDetails.spans || traceDetails.spans.length === 0) {
      return traceDetails?.duration;
    }

    // If duration is already provided and valid, use it
    if (traceDetails.duration && traceDetails.duration > 0) {
      return traceDetails.duration;
    }

    // Otherwise, calculate from spans: find the earliest start and latest end
    const spans = traceDetails.spans;
    const startTimes = spans.map((s: Span) => s.startTime).filter((t: number) => t > 0);
    const endTimes = spans.map((s: Span) => s.startTime + s.duration).filter((t: number) => t > 0);

    if (startTimes.length === 0 || endTimes.length === 0) {
      return traceDetails.duration;
    }

    const earliestStart = Math.min(...startTimes);
    const latestEnd = Math.max(...endTimes);

    const calculatedDuration = latestEnd - earliestStart;

    if (calculatedDuration > 0) {
      console.log("Calculated trace duration from spans:", calculatedDuration, "microseconds (", (calculatedDuration / 1000000).toFixed(2), "s)");
      return calculatedDuration;
    }

    return traceDetails.duration;
  }, [traceDetails]);

  const getServiceName = (trace: Trace) => {
    if (trace.processes && Object.keys(trace.processes).length > 0) {
      const firstProcess = Object.values(trace.processes)[0];
      return firstProcess.serviceName || "Unknown";
    }
    return "Unknown";
  };

  const getMainOperation = (trace: Trace) => {
    if (!trace.spans || trace.spans.length === 0) return "Unknown Operation";
    const rootSpan = trace.spans.find(s => !s.references || s.references.length === 0) || trace.spans[0];
    return rootSpan.operationName;
  };

  // Extract client IP address from trace spans
  const getClientIP = (trace: Trace): string | null => {
    if (!trace.spans || trace.spans.length === 0) return null;

    // Look for IP in any span (usually in the root HTTP request span)
    for (const span of trace.spans) {
      const tags = span.tags || [];
      // Check for client.ip or http.client_ip attributes
      const ipTag = tags.find(t =>
        t.key === "client.ip" ||
        t.key === "http.client_ip" ||
        t.key.toLowerCase() === "client.ip" ||
        t.key.toLowerCase() === "http.client_ip"
      );
      if (ipTag && ipTag.value && String(ipTag.value) !== "unknown") {
        return String(ipTag.value);
      }
    }
    return null;
  };

  return (
    <>
      <Head>
        <title>{`Trace Viewer - ${getPlatformName()}`}</title>
        <meta name="description" content="View and analyze request traces" />
      </Head>

      <ContentLayout>
        <VStack spacing={6} w="full" align="stretch" maxW="100%">
          <ManagementPageHeader
            title="Trace Viewer"
            description="View and analyze request execution traces"
          />

          {/* Show auth warning if not authenticated */}
          {!authLoading && !isAuthenticated && (
            <Alert status="warning">
              <AlertIcon />
              <AlertDescription>
                Please log in to view traces.{" "}
                <Button
                  size="sm"
                  colorScheme="blue"
                  ml={4}
                  onClick={() => router.push("/auth")}
                >
                  Log In
                </Button>
              </AlertDescription>
            </Alert>
          )}

          {/* Trace ID Search */}
          <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" w="full">
            <CardBody>
              <FormControl>
                <FormLabel fontWeight="medium" color="gray.700" mb={2}>
                  Search by Trace ID
                </FormLabel>
                  <HStack spacing={2}>
                    <Input
                    placeholder="Enter trace ID (e.g., 741229d83d4d22e4de3e9abddaf37e01)..."
                      value={traceIdSearch}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTraceIdSearch(e.target.value)}
                      bg="white"
                      fontFamily="mono"
                      fontSize="sm"
                    size="lg"
                    onKeyPress={(e: React.KeyboardEvent<HTMLInputElement>) => {
                        if (e.key === "Enter") {
                          handleSearchByTraceId();
                        }
                      }}
                    />
                    <Button
                    colorScheme="blue"
                      onClick={handleSearchByTraceId}
                      isDisabled={!traceIdSearch.trim()}
                      leftIcon={<SearchIcon />}
                    size="lg"
                    >
                    Load Trace
                    </Button>
                  </HStack>
                </FormControl>
            </CardBody>
          </Card>

          {/* Trace Details */}
          {traceDetailsLoading ? (
            <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" w="full">
              <CardBody>
                <Flex justify="center" align="center" py={12}>
                  <Spinner size="xl" />
                  <Text ml={4}>Loading trace details...</Text>
                </Flex>
              </CardBody>
            </Card>
          ) : traceError ? (
            <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" w="full">
              <CardBody>
                <Alert status="error">
                  <AlertIcon />
                  <AlertDescription>
                    Failed to load trace. {(traceError as any)?.message || "Trace not found or not accessible."}
                  </AlertDescription>
                </Alert>
              </CardBody>
            </Card>
          ) : traceDetails ? (
            <VStack spacing={4} w="full" align="stretch">
              {/* Trace Summary Header */}
              <Card bgGradient={bgGradient} border="1px" borderColor={borderColor} boxShadow="md" w="full">
                <CardBody>
                  <VStack spacing={4} align="stretch">
                    <Box>
                      <Heading size="md" mb={2} color="gray.800">
                        {getServiceName(traceDetails)}: {getMainOperation(traceDetails)}
                      </Heading>
                      <Text fontFamily="mono" fontSize="xs" color="gray.600">
                        Trace ID: {traceDetails.traceID}
                      </Text>
                    </Box>

                    <HStack spacing={6} flexWrap="wrap" align="flex-start">
                      <Box minH="50px">
                        <Text fontSize="xs" color="gray.600" mb={1}>
                          Started
                        </Text>
                        <Text fontSize="sm" fontWeight="medium" color="gray.700">
                          {formatTimestamp(traceStartTime)}
                        </Text>
                      </Box>
                      <Box minH="50px">
                        <Text fontSize="xs" color="gray.600" mb={1}>
                          Duration
                        </Text>
                        <Text fontSize="sm" fontWeight="medium" color="gray.700">
                          {formatDuration(traceDuration)}
                        </Text>
                      </Box>
                      <Box minH="50px">
                        <Text fontSize="xs" color="gray.600" mb={1}>
                          Steps
                        </Text>
                        <Text fontSize="sm" fontWeight="medium" color="gray.700">
                          {processedSpans.length}
                        </Text>
                      </Box>
                      {getClientIP(traceDetails) && (
                        <Box minH="50px">
                          <Text fontSize="xs" color="gray.600" mb={1}>
                            Client IP
                          </Text>
                          <Text fontSize="sm" fontWeight="medium" color="gray.700" fontFamily="mono">
                            {getClientIP(traceDetails)}
                          </Text>
                        </Box>
                      )}
                      <Box minH="50px" display="flex" flexDirection="column" flex={1} minW="200px">
                        <Text fontSize="xs" color="gray.600" mb={1}>
                          Status
                        </Text>
                        <HStack spacing={2} align="center" flexWrap="wrap">
                          <Badge
                            colorScheme={traceStatus.status === "success" ? "green" : traceStatus.status === "error" ? "red" : "yellow"}
                            fontSize="sm"
                            px={2}
                            py={1}
                            display="inline-flex"
                            alignItems="center"
                            height="fit-content"
                            lineHeight="1.5"
                          >
                            {traceStatus.status === "success" && <Icon as={CheckCircleIcon} mr={1} boxSize={3} />}
                            {traceStatus.message}
                          </Badge>
                          {traceStatus.status === "error" && primaryErrorMessage && (
                            <Text
                              fontSize="xs"
                              color="red.600"
                              fontWeight="bold"
                              bg="red.50"
                              px={2}
                              py={1}
                              borderRadius="md"
                              border="1px solid"
                              borderColor="red.200"
                              maxW="500px"
                            >
                              {primaryErrorMessage}
                            </Text>
                          )}
                        </HStack>
                      </Box>
              </HStack>
                  </VStack>
            </CardBody>
          </Card>

              {/* Main Content: Two Column Layout */}
              <Grid templateColumns={{ base: "1fr", lg: "1fr 1fr" }} gap={6} w="full">
                {/* Left Column: User Interface (What the user sees) */}
            <GridItem minW="0">
                  <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" h="full">
                    <CardBody>
                      <VStack spacing={4} align="stretch">
                        <Box>
                          <HStack spacing={2} align="center" mb={1}>
                            <Icon as={FiEye} color="blue.500" boxSize={5} />
                            <Heading size="sm" color="gray.700">
                              User Interface
                            </Heading>
                          </HStack>
                          <Text fontSize="xs" color="gray.500" pl={7}>
                            (What the user sees)
                    </Text>
                  </Box>

                        <Divider />

                        {/* Request Summary */}
                        <Box>
                          <HStack mb={2} align="center">
                            <Icon as={FiInfo} color="blue.500" boxSize={4} />
                            <Text fontSize="sm" fontWeight="medium" color="gray.600">
                              Request Summary
                            </Text>
                          </HStack>
                          <Box p={4} bg="blue.50" borderRadius="md" border="1px" borderColor="blue.200" boxShadow="sm">
                            <VStack align="start" spacing={2}>
                              <HStack spacing={2} align="center">
                                <Icon as={FiGlobe} color="blue.600" boxSize={4} />
                                <Text fontSize="sm" fontWeight="semibold" color="blue.800">
                                  {getServiceName(traceDetails)}: {getMainOperation(traceDetails)}
                                </Text>
                              </HStack>
                              <HStack spacing={2} align="center" pl={6}>
                                <Text fontSize="xs" color="blue.600" fontFamily="mono">
                                  ID: {traceDetails.traceID.slice(0, 16)}...
                                </Text>
                              </HStack>
                            </VStack>
                          </Box>
                        </Box>

                        {/* Activity Log */}
                        <Box>
                          <HStack mb={2} align="center">
                            <Icon as={FiClock} color="orange.500" boxSize={4} />
                            <Text fontSize="sm" fontWeight="medium" color="gray.600">
                              Activity Log
                            </Text>
                          </HStack>
                          <VStack spacing={2} align="stretch" maxH="400px" overflowY="auto">
                            {processedSpans && processedSpans.length > 0 ? (
                              processedSpans.map((processed: ProcessedSpan, idx: number) => {
                                const relativeTime = formatRelativeTime(processed.relativeStart);
                                const duration = formatDuration(processed.effectiveDuration ?? processed.span.duration);
                                return (
                                  <Box
                                    key={idx}
                            p={3}
                                    bg={processed.hasError ? "red.50" : "white"}
                                    borderRadius="md"
                                    borderLeft="4px solid"
                                    borderLeftColor={
                                      processed.hasError || processed.category === "error" ? "red.500" :
                                      processed.category === "auth" ? "green.500" :
                                      processed.category === "processing" ? "blue.500" :
                                      processed.category === "routing" ? "purple.500" :
                                      "gray.400"
                                    }
                                    boxShadow="sm"
                                    _hover={{ boxShadow: "md", transform: "translateX(2px)" }}
                            transition="all 0.2s"
                          >
                                    <HStack justify="space-between" mb={2} align="start">
                                      <HStack spacing={2} align="center">
                                        <Icon
                                          as={processed.icon}
                                          color={
                                            processed.hasError || processed.category === "error" ? "red.500" :
                                            processed.category === "auth" ? "green.500" :
                                            processed.category === "processing" ? "blue.500" :
                                            processed.category === "routing" ? "purple.500" :
                                            "gray.500"
                                          }
                                          boxSize={4}
                                        />
                                        <VStack align="start" spacing={0}>
                                          <HStack spacing={2} align="center" flexWrap="wrap">
                                            <Text fontSize="sm" color={processed.hasError ? "red.700" : "gray.700"} fontWeight="semibold">
                                              {processed.displayName}
                                            </Text>
                                            {processed.hasError && (
                                              <>
                                                <Badge colorScheme="red" fontSize="xx-small" px={1.5} py={0.5} borderRadius="full">
                                                  FAILED
                                                </Badge>
                                                {processed.errorMessage && (
                                                  <Text
                                                    fontSize="xs"
                                                    color="red.600"
                                                    fontWeight="bold"
                                                    bg="red.50"
                                                    px={2}
                                                    py={0.5}
                                                    borderRadius="md"
                                                    border="1px solid"
                                                    borderColor="red.200"
                                                  >
                                                    {processed.errorMessage}
                                                  </Text>
                                                )}
                                              </>
                                            )}
                                          </HStack>
                                          <Text fontSize="xs" color="gray.500" fontFamily="mono">
                                            +{relativeTime} since start
                                </Text>
                                        </VStack>
                                      </HStack>
                                      <Badge fontSize="xs" colorScheme={processed.hasError ? "red" : "orange"} px={2} py={1} borderRadius="full" textTransform="none">
                                        {duration}
                                  </Badge>
                                </HStack>
                                    <Text fontSize="xs" color={processed.hasError ? "red.700" : "gray.600"} pl={6} fontWeight={processed.hasError ? "medium" : "normal"}>
                                      {processed.hasError && processed.errorMessage
                                        ? `❌ ${processed.errorMessage}`
                                        : getUserFriendlyDescription(processed)}
                                </Text>
                          </Box>
                                );
                              })
                            ) : traceDetails?.spans && traceDetails.spans.length > 0 ? (
                              <Box>
                                <Text fontSize="sm" color="orange.600" textAlign="center" py={2} fontWeight="medium">
                                  ⚠️ Spans found but not processed
                      </Text>
                                <Text fontSize="xs" color="gray.500" textAlign="center">
                                  Check browser console for details. Total spans: {traceDetails.spans.length}
                      </Text>
                              </Box>
                  ) : (
                              <Text fontSize="sm" color="gray.500" textAlign="center" py={4}>
                                Waiting for activity...
                      </Text>
                      )}
                    </VStack>
                    </Box>
                      </VStack>
                </CardBody>
              </Card>
            </GridItem>

                {/* Right Column: Behind the Scenes (What the orchestrator does) */}
            <GridItem minW="0">
                  <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" h="full">
                  <CardBody>
                      <VStack spacing={4} align="stretch">
                        <Box>
                          <HStack spacing={2} align="center" mb={1}>
                            <Icon as={FiLayers} color="purple.500" boxSize={5} />
                            <Heading size="sm" color="gray.700">
                              Behind the Scenes
                      </Heading>
                          </HStack>
                          <Text fontSize="xs" color="gray.500" pl={7}>
                            (What the orchestrator does)
                      </Text>
                    </Box>

                        <Divider />

                        {/* Step-by-step visualization */}
                        <VStack spacing={3} align="stretch">
                          {processedSpans && processedSpans.length > 0 ? (
                            processedSpans.map((processed: ProcessedSpan, idx: number) => {
                            const duration = formatDuration(processed.effectiveDuration ?? processed.span.duration);

                            // Merge tags from current span and all ancestor spans
                            // Parent tags are useful for input-related info (e.g., nmt.input.* on parent nmt.inference)
                            // But filter out redundant tags to avoid repetition
                            let allTags = [...(processed.span.tags || [])];
                            const childTagKeys = new Set(allTags.map(t => t.key.toLowerCase()));

                            // Tags to exclude from parent spans (redundant HTTP metadata)
                            const redundantHttpTags = new Set([
                              'http.host', 'http.method', 'http.route', 'http.server_name',
                              'http.target', 'http.url', 'http.user_agent', 'correlation.header'
                            ]);

                            const isServiceDomainTag = (tagKey: string): boolean =>
                              tagKey.startsWith('nmt.') ||
                              tagKey.startsWith('ocr.') ||
                              tagKey.startsWith('transliteration.') ||
                              tagKey.startsWith('audio-lang-detection.') ||
                              tagKey.startsWith('speaker-diarization.') ||
                              tagKey.startsWith('language-diarization.') ||
                              tagKey.startsWith('language-detection.') ||
                              tagKey.startsWith('ner.') ||
                              tagKey.startsWith('pipeline.') ||
                              tagKey.startsWith('tts.') ||
                              tagKey.startsWith('asr.');

                            /** Merge only parent tags that belong to that phase (Telemetry Step Standardization). */
                            const shouldIncludeParentTagForStandardPhase = (
                              tagKey: string,
                              spanCategory: string
                            ): boolean => {
                              const infra =
                                tagKey === 'correlation.id' ||
                                tagKey === 'organization' ||
                                tagKey.startsWith('user.') ||
                                tagKey.startsWith('session.') ||
                                tagKey.startsWith('api_key') ||
                                tagKey.includes('tenant') ||
                                tagKey === 'client.ip' ||
                                tagKey === 'http.client_ip';

                              if (spanCategory === 'phase.persist') {
                                if (infra) return true;
                                if (tagKey.endsWith('.service_id')) return true;
                                // Persist span should carry DB attrs from the exporter; do not pull input/output/model from ancestors.
                                if (isServiceDomainTag(tagKey)) return false;
                                return false;
                              }

                              if (spanCategory === 'phase.preprocess') {
                                if (infra) return true;
                                if (tagKey.endsWith('.service_id')) return true;
                                if (tagKey.includes('source_language') || tagKey.includes('target_language')) return true;
                                if (
                                  tagKey.includes('.input.') ||
                                  tagKey.includes('input_count') ||
                                  tagKey.includes('input_size') ||
                                  tagKey.includes('request.size') ||
                                  tagKey.startsWith('http.request') ||
                                  tagKey.includes('input_type')
                                )
                                  return true;
                                if (tagKey.includes('audio_format') || tagKey.includes('sampling_rate')) return true;
                                if (tagKey.includes('image_count') || tagKey.includes('image_bytes')) return true;
                                if (isServiceDomainTag(tagKey)) {
                                  if (tagKey.includes('.output.') || tagKey.includes('output_count')) return false;
                                  if (tagKey.includes('.db_') || tagKey.includes('request_id')) return false;
                                  if (tagKey.endsWith('.model_name') || tagKey.includes('triton_endpoint')) return false;
                                  if (
                                    tagKey.endsWith('.processing_time_seconds') ||
                                    tagKey.endsWith('.status')
                                  )
                                    return false;
                                  return true;
                                }
                                if (tagKey.startsWith('triton.')) return false;
                                return false;
                              }

                              if (spanCategory === 'phase.resolve_model') {
                                if (infra) return true;
                                // Span exporter should set *.resolve_model.* / model endpoint attrs; do not pull
                                // inference context (languages, input_type, service_id) from ancestors.
                                if (isServiceDomainTag(tagKey)) return false;
                                return false;
                              }

                              if (spanCategory === 'phase.triton_inference') {
                                if (infra) return true;
                                // Phase span should carry *.triton_inference.* from the exporter; do not merge
                                // generic inference attrs from ancestors (languages, service_id, etc.).
                                if (isServiceDomainTag(tagKey)) return false;
                                if (tagKey.startsWith('triton.')) return false;
                                return false;
                              }

                              if (spanCategory === 'phase.postprocess') {
                                if (infra) return true;
                                // Postprocess span owns *.postprocess.* and *.output.* from the exporter only.
                                if (isServiceDomainTag(tagKey)) return false;
                                if (tagKey.startsWith('triton.')) return false;
                                return false;
                              }

                              return false;
                            };

                            // Helper function to determine if a parent tag should be included
                            const shouldIncludeParentTag = (tagKey: string, spanCategory: string): boolean => {
                              // Always exclude redundant HTTP metadata from parent spans
                              if (redundantHttpTags.has(tagKey)) return false;

                              if (spanCategory.startsWith('phase.')) {
                                return shouldIncludeParentTagForStandardPhase(tagKey, spanCategory);
                              }

                              // For processing spans, include input/output data from parents
                              if (spanCategory === 'processing') {
                                return tagKey.includes('.input.') ||
                                       tagKey.includes('input_count') ||
                                       tagKey.includes('input_size') ||
                                       tagKey.includes('request.size') ||
                                       tagKey.startsWith('http.request') ||
                                       tagKey.startsWith('nmt.') ||
                                       tagKey.startsWith('ocr.') ||
                                       tagKey.startsWith('transliteration.') ||
                                       tagKey.startsWith('audio-lang-detection.') ||
                                       tagKey.startsWith('speaker-diarization.') ||
                                       tagKey.startsWith('language-diarization.') ||
                                       tagKey.startsWith('language-detection.') ||
                                       tagKey.startsWith('ner.') ||
                                       tagKey.startsWith('pipeline.') ||
                                       tagKey.startsWith('tts.') ||
                                       tagKey.startsWith('asr.') ||
                                       tagKey.startsWith('triton.') ||
                                       tagKey === 'correlation.id' ||
                                       tagKey === 'organization' ||
                                       tagKey.startsWith('user.') ||
                                       tagKey === 'client.ip' ||
                                       tagKey === 'http.client_ip';
                              }

                              // For auth spans, include auth-related and organization tags
                              if (spanCategory === 'auth') {
                                return tagKey.startsWith('auth.') ||
                                       tagKey === 'organization' ||
                                       tagKey.startsWith('user.') ||
                                       tagKey === 'correlation.id' ||
                                       tagKey === 'client.ip' ||
                                       tagKey === 'http.client_ip';
                              }

                              // For other spans, only include essential tags
                              return tagKey === 'correlation.id' ||
                                     tagKey === 'organization' ||
                                     tagKey.startsWith('user.') ||
                                     tagKey.includes('.input.') ||
                                     tagKey.includes('input_count') ||
                                     tagKey === 'client.ip' ||
                                     tagKey === 'http.client_ip';
                            };

                            // Traverse up the parent chain to collect tags from all ancestors
                            let currentParentId = spanRelationships.spanToParent.get(processed.span.spanID);
                            const visitedParents = new Set<string>(); // Prevent infinite loops

                            while (currentParentId && !visitedParents.has(currentParentId)) {
                              visitedParents.add(currentParentId);
                              const parentSpan = spanRelationships.spanMap.get(currentParentId);

                              if (parentSpan && parentSpan.tags) {
                                // Add parent tags that don't exist in child and are relevant
                                parentSpan.tags.forEach((parentTag: { key: string; value: any }) => {
                                  const tagKey = parentTag.key.toLowerCase();
                                  if (!childTagKeys.has(tagKey) &&
                                      shouldIncludeParentTag(tagKey, processed.category)) {
                                    allTags.push(parentTag);
                                    childTagKeys.add(tagKey); // Track added tags to avoid duplicates
                                  }
                                });
                              }

                              // Move to next parent level
                              currentParentId = spanRelationships.spanToParent.get(currentParentId);
                            }

                            // Traverse down to child spans to collect triton.* and internal.* tags
                            // This is important because triton tags might be on child spans (e.g., triton.inference under ocr.triton_batch)
                            const collectTagsFromChildren = (spanId: string, visited: Set<string>) => {
                              if (visited.has(spanId)) return; // Prevent infinite loops
                              visited.add(spanId);

                              const childSpanIds = spanRelationships.childSpans.get(spanId) || [];
                              childSpanIds.forEach((childSpanId: string) => {
                                const childSpan = spanRelationships.spanMap.get(childSpanId);
                                if (childSpan && childSpan.tags) {
                                  childSpan.tags.forEach((childTag: { key: string; value: any }) => {
                                    const tagKey = childTag.key.toLowerCase();
                                    // Always include triton.* and internal.* tags from children
                                    if ((tagKey.startsWith("triton.") || tagKey.startsWith("internal.")) &&
                                        !childTagKeys.has(tagKey)) {
                                      allTags.push(childTag);
                                      childTagKeys.add(tagKey);
                                    }
                                  });
                                }
                                // Recursively collect from grandchildren
                                collectTagsFromChildren(childSpanId, visited);
                              });
                            };

                            // Collect triton and internal tags from all child spans.
                            // Exception: for the standard Triton phase span (e.g., nmt.triton_inference),
                            // keep child tags separated so the UI can show triton.inference as an indented child
                            // with its own technical details.
                            if (processed.category !== "phase.triton_inference") {
                              const visitedChildren = new Set<string>();
                              collectTagsFromChildren(processed.span.spanID, visitedChildren);
                            }

                            const relevantTags = allTags.filter((t: { key: string; value: any }) => {
                              const key = t.key.toLowerCase();

                              // PRIORITY: Always include triton.* tags FIRST (important for AI Model Inference spans)
                              // This ensures they're never filtered out by other rules
                              if (key.startsWith("triton.")) {
                                return true;
                              }

                              // PRIORITY: Always include internal.* tags (span metadata)
                              if (key.startsWith("internal.")) {
                                return true;
                              }

                              // Filter out truly irrelevant tags
                              if (key.includes("telemetry.") ||
                                  key.includes("http.flavor") ||
                                  key.includes("http.scheme") ||
                                  key.includes("net.") ||
                                  key.includes("correlation.generated") ||
                                  key === "span.kind") {
                                return false;
                              }

                              // For non-top-level spans, filter out redundant HTTP metadata
                              // Keep essential HTTP tags: status_code, request/response size_bytes
                              // Remove verbose HTTP metadata: host, method, route, server_name, target, url, user_agent
                              // But only if this is not a top-level processing span (which should show full HTTP context)
                              if (!processed.isTopLevel && key.startsWith("http.") &&
                                  key !== "http.status_code" &&
                                  key !== "http.request.size_bytes" &&
                                  key !== "http.response.size_bytes") {
                                return false;
                              }

                              // Keep otel.status_code, otel.status_description (for errors), and otel.scope.name, filter out other otel.*
                              if (key.includes("otel.") &&
                                  key !== "otel.status_code" &&
                                  key !== "otel.status_description" &&
                                  key !== "otel.scope.name") {
                                return false;
                              }

                              // Always include error-related tags for error spans
                              if (processed.hasError && (
                                key.includes("error") ||
                                key.includes("exception") ||
                                key === "db.statement" ||
                                key === "db.system" ||
                                key === "db.name"
                              )) {
                                return true;
                              }

                              return true;
                            });

                            // Sort tags to prioritize important ones first
                            relevantTags.sort((a: { key: string; value: any }, b: { key: string; value: any }) => {
                              const aKey = a.key.toLowerCase();
                              const bKey = b.key.toLowerCase();

                              // Priority order: error tags (for errors) > input tags > service-specific tags > http status > organization > correlation.id > user.id > otel scope > others
                              const getPriority = (key: string): number => {
                                // Highest priority for errors: error-related tags
                                if (processed.hasError) {
                                  if (key === "otel.status_description") return -2;
                                  if (key.includes("error") || key.includes("exception")) return -1;
                                  if (key === "db.statement" || key === "db.system") return 0;
                                }
                                if (
                                  processed.category === "phase.persist" &&
                                  (key.includes(".db.") ||
                                    key.includes("request_id") ||
                                    key.includes("pii_redact"))
                                ) {
                                  return 0.25;
                                }
                                if (
                                  processed.category === "phase.resolve_model" &&
                                  (key.includes("resolve_model") ||
                                    key.includes("model_name") ||
                                    key.includes("triton_endpoint") ||
                                    key.includes("infer_endpoint") ||
                                    key.includes("triton_client"))
                                ) {
                                  return 0.25;
                                }
                                if (
                                  processed.category === "phase.triton_inference" &&
                                  (key.includes("triton_inference") ||
                                    key.startsWith("triton."))
                                ) {
                                  return 0.25;
                                }
                                if (
                                  processed.category === "phase.postprocess" &&
                                  (key.includes("postprocess") ||
                                    key.includes(".output.") ||
                                    key.includes("output_count") ||
                                    key.includes("formatted_count"))
                                ) {
                                  return 0.25;
                                }
                                // Highest priority: input-related tags (most important for understanding the request)
                                if (key.includes(".input.") || key.includes("input_count") || key.includes("input_size") ||
                                    key.includes("request.size") || key.startsWith("http.request")) return 1;
                                // High priority: client IP (important for request tracking)
                                if (key === "client.ip" || key === "http.client_ip") return 1.5;
                                // High priority: service-specific tags (including triton tags for AI Model Inference)
                                if (key.startsWith("nmt.") || key.startsWith("ocr.") || key.startsWith("transliteration.") || key.startsWith("audio-lang-detection.") || key.startsWith("speaker-diarization.") || key.startsWith("language-diarization.") || key.startsWith("language-detection.") || key.startsWith("ner.") || key.startsWith("pipeline.") || key.startsWith("tts.") || key.startsWith("asr.") || key.startsWith("triton.")) return 2;
                                if (key === "http.status_code" || key === "otel.status_code") return 3;
                                if (key === "organization") return 4;
                                if (key === "correlation.id") return 5;
                                if (key.startsWith("user.")) return 6;
                                if (key.startsWith("http.")) return 7;
                                if (key === "otel.scope.name") return 8;
                                return 9;
                              };

                              return getPriority(aKey) - getPriority(bKey);
                            });

                            // Calculate depth for indentation - only count displayed parent spans
                            // This ensures indentation reflects the visible hierarchy
                            const calculateDisplayedDepth = (spanId: string): number => {
                              let depth = 0;
                              let currentId: string | undefined = spanId;
                              const visited = new Set<string>();
                              const displayedSpanIds = new Set(processedSpans?.map((p: ProcessedSpan) => p.span.spanID) || []);

                              while (currentId) {
                                if (visited.has(currentId)) break; // Prevent infinite loops
                                visited.add(currentId);

                                const parentId: string | undefined = spanRelationships.spanToParent.get(currentId);
                                if (parentId) {
                                  // Only increment depth if the parent is actually displayed
                                  if (displayedSpanIds.has(parentId)) {
                                    depth++;
                                  }
                                  // Continue traversing up the chain
                                  currentId = parentId;
                                } else {
                                  break;
                                }
                              }

                              return depth;
                            };

                            const depth = calculateDisplayedDepth(processed.span.spanID);
                            const indentPx = depth * 24; // 24px per level of nesting

                            // Calculate sum of visible child spans to explain duration discrepancy
                            const childSpans = processedSpans?.filter((p: ProcessedSpan) => {
                              const parentId = spanRelationships.spanToParent.get(p.span.spanID);
                              return parentId === processed.span.spanID;
                            }) || [];

                            const childSpansDuration = childSpans.reduce((sum: number, child: ProcessedSpan) => {
                              return sum + (child.span.duration || 0);
                            }, 0);

                            const parentDuration = processed.span.duration || 0;
                            const overheadTime = parentDuration - childSpansDuration;
                            const hasSignificantOverhead = overheadTime > 1000 && childSpans.length > 0; // > 1ms overhead with visible children

                            return (
                              <Card
                                key={idx}
                                bg={processed.hasError ? "red.50" : "white"}
                                border="1px"
                                borderColor={processed.hasError ? "red.300" : borderColor}
                                borderLeft={processed.hasError ? "4px solid" : "1px"}
                                borderLeftColor={processed.hasError ? "red.500" : undefined}
                                boxShadow="sm"
                                borderRadius="lg"
                                overflow="hidden"
                                ml={indentPx > 0 ? `${indentPx}px` : 0}
                                _hover={{
                                  bg: processed.hasError ? "red.50" : "blue.50",
                                  borderColor: processed.hasError ? "red.300" : "blue.300",
                                  boxShadow: "md",
                                  transform: "translateY(-2px)",
                                  transition: "all 0.2s"
                                }}
                                transition="all 0.2s"
                                cursor="pointer"
                              >
                                <CardBody>
                                  <VStack spacing={3} align="stretch">
                                    {/* Header with icon and title */}
                                    <HStack spacing={3} align="start">
                                      <Box
                                        p={2.5}
                                        borderRadius="lg"
                                        bg={
                                          processed.hasError || processed.category === "error" ? "red.50" :
                                          processed.category === "auth" ? "green.50" :
                                          processed.category === "processing" ? "blue.50" :
                                          processed.category === "routing" ? "purple.50" :
                                          "gray.50"
                                        }
                                        border="1px"
                                        borderColor={
                                          processed.hasError || processed.category === "error" ? "red.200" :
                                          processed.category === "auth" ? "green.200" :
                                          processed.category === "processing" ? "blue.200" :
                                          processed.category === "routing" ? "purple.200" :
                                          "gray.200"
                                        }
                                        flexShrink={0}
                                      >
                                        <Icon
                                          as={processed.icon}
                                          color={
                                            processed.hasError || processed.category === "error" ? "red.600" :
                                            processed.category === "auth" ? "green.600" :
                                            processed.category === "processing" ? "blue.600" :
                                            processed.category === "routing" ? "purple.600" :
                                            "gray.600"
                                          }
                                          boxSize={5}
                                        />
                            </Box>
                                      <VStack align="start" spacing={1} flex={1}>
                                        <HStack spacing={2} align="center" w="full" flexWrap="wrap">
                                          <Text fontSize="sm" fontWeight="bold" color={processed.hasError ? "red.700" : "gray.700"} flex={1}>
                                            {processed.displayName}
                              </Text>
                                          {processed.hasError ? (
                                            <HStack spacing={2} align="center" flexWrap="wrap">
                                              <Badge colorScheme="red" fontSize="xx-small" px={2} py={0.5} borderRadius="full">
                                                FAILED
                                              </Badge>
                                              {processed.errorMessage && (
                                                <Text
                                                  fontSize="xs"
                                                  color="red.600"
                                                  fontWeight="bold"
                                                  bg="red.50"
                                                  px={2}
                                                  py={0.5}
                                                  borderRadius="md"
                                                  border="1px solid"
                                                  borderColor="red.200"
                                                  maxW="400px"
                                                >
                                                  {processed.errorMessage}
                                                </Text>
                                              )}
                                            </HStack>
                                          ) : traceStatus.status === "success" && (
                                            <Icon as={CheckCircleIcon} color="green.500" boxSize={4} />
                                          )}
                                        </HStack>
                                        <Badge
                                          fontSize="xs"
                                          colorScheme={
                                            processed.hasError || processed.category === "error" ? "red" :
                                            processed.category === "auth" ? "green" :
                                            processed.category === "processing" ? "blue" :
                                            processed.category === "routing" ? "purple" :
                                            "gray"
                                          }
                                          px={2}
                                          py={0.5}
                                          borderRadius="full"
                                          textTransform="none"
                                        >
                                          {duration}
                                        </Badge>
                                      </VStack>
                                    </HStack>

                                    {/* User-friendly description */}
                                    {(() => {
                                      const errorDetails = processed.hasError ? parseErrorDetails(processed) : null;

                                      if (errorDetails) {
                                        // Display structured error details
                                        return (
                                          <Box>
                                            {/* Error Summary */}
                                            <Box
                                              p={3}
                                              bg="red.50"
                                              borderRadius="md"
                                              borderLeft="4px solid"
                                              borderLeftColor="red.500"
                                              boxShadow="sm"
                                              mb={3}
                                              overflow="hidden"
                                              w="full"
                                            >
                                              <HStack spacing={2} mb={2} align="center">
                                                <Icon as={FiInfo} color="red.600" boxSize={4} />
                                                <Text fontSize="sm" color="red.700" fontWeight="bold">
                                                  {errorDetails.errorType}
                                                </Text>
                                              </HStack>
                                              <Text
                                                fontSize="xs"
                                                color="red.800"
                                                lineHeight="1.6"
                                                pl={6}
                                                fontWeight="medium"
                                              >
                                                {errorDetails.summary}
                                              </Text>
                                            </Box>

                                            {/* Error Details Table */}
                                            {errorDetails.fields.length > 0 && (
                                              <Box
                                                p={3}
                                                bg="red.100"
                                                borderRadius="md"
                                                border="1px solid"
                                                borderColor="red.300"
                                                boxShadow="sm"
                                                overflow="hidden"
                                                w="full"
                                              >
                                                <HStack spacing={2} mb={3} align="center">
                                                  <Icon as={FiSettings} color="red.700" boxSize={3} />
                                                  <Text fontSize="xs" color="red.800" fontWeight="semibold">
                                                    Error Details:
                                                  </Text>
                                                </HStack>
                                                <VStack spacing={2} align="stretch">
                                                  {errorDetails.fields.map((field, idx) => (
                                                    <Box
                                                      key={idx}
                                                      p={2}
                                                      bg="white"
                                                      borderRadius="sm"
                                                      border="1px solid"
                                                      borderColor="red.200"
                                                      overflow="hidden"
                                                      w="full"
                                                    >
                                                      <HStack spacing={3} align="start">
                                                        <Text
                                                          fontSize="xs"
                                                          fontWeight="bold"
                                                          color="red.700"
                                                          minW="120px"
                                                          maxW="120px"
                                                        >
                                                          {field.key}:
                                                        </Text>
                                                        <Text
                                                          fontSize="xs"
                                                          color="red.900"
                                                          fontFamily="mono"
                                                          wordBreak="break-word"
                                                          flex={1}
                                                          whiteSpace="pre-wrap"
                                                        >
                                                          {field.value}
                                                        </Text>
                                                      </HStack>
                                                    </Box>
                                                  ))}
                                                </VStack>
                                              </Box>
                                            )}
                                          </Box>
                                        );
                                      } else {
                                        // Display normal description for non-error spans
                                        return (
                                          <Box
                                            p={3}
                                            bg="blue.50"
                                            borderRadius="md"
                                            borderLeft="3px solid"
                                            borderLeftColor="blue.400"
                                            boxShadow="sm"
                                          >
                                            <HStack spacing={2} mb={1} align="center">
                                              <Icon as={FiInfo} color="blue.600" boxSize={3} />
                                              <Text fontSize="xs" color="blue.700" fontWeight="medium">
                                                What this step does:
                                              </Text>
                                            </HStack>
                                            <Text
                                              fontSize="xs"
                                              color="gray.700"
                                              lineHeight="1.6"
                                              pl={5}
                                            >
                                              {getUserFriendlyDescription(processed)}
                                            </Text>
                                          </Box>
                                        );
                                      }
                                    })()}

                                    {/* Duration overhead explanation - show when parent has significant overhead vs children */}
                                    {hasSignificantOverhead && (
                                      <Box
                                        p={2}
                                        bg="yellow.50"
                                        borderRadius="md"
                                        borderLeft="3px solid"
                                        borderLeftColor="yellow.400"
                                        boxShadow="sm"
                                      >
                                        <HStack spacing={2} align="start">
                                          <Icon as={FiInfo} color="yellow.700" boxSize={3} mt={0.5} flexShrink={0} />
                                          <VStack align="start" spacing={0.5} flex={1}>
                                            <Text fontSize="xs" color="yellow.800" fontWeight="medium">
                                              Duration Breakdown:
                                            </Text>
                                            <Text fontSize="xs" color="yellow.700" lineHeight="1.4">
                                              This step duration ({formatDuration(parentDuration)}) includes {childSpans.length} visible child step{childSpans.length !== 1 ? 's' : ''} ({formatDuration(childSpansDuration)}) plus {formatDuration(overheadTime)} of overhead (framework processing, middleware, network latency, and filtered spans not shown here).
                                            </Text>
                                          </VStack>
                                        </HStack>
                                      </Box>
                                    )}

                                    {/* Technical details - collapsible */}
                                    {relevantTags.length > 0 && (
                                      <Box>
                                        <Button
                                          variant="outline"
                                          colorScheme="gray"
                                          width="full"
                                          h="22px"
                                          minH="22px"
                                          maxH="22px"
                                          fontSize="10px"
                                          px={2}
                                          py={0}
                                          lineHeight="1.2"
                                          sx={{
                                            '& .chakra-button__icon': {
                                              marginInlineEnd: '6px',
                                            }
                                          }}
                                          leftIcon={<Icon as={expandedTags.has(processed.span.spanID) ? FiEyeOff : FiEye} boxSize={2.5} />}
                                          onClick={() => {
                                            const spanId = processed.span.spanID;
                                            const newExpanded = new Set(expandedTags);
                                            if (newExpanded.has(spanId)) {
                                              newExpanded.delete(spanId);
                                            } else {
                                              newExpanded.add(spanId);
                                            }
                                            setExpandedTags(newExpanded);
                                          }}
                                        >
                                          {expandedTags.has(processed.span.spanID)
                                            ? "Hide Technical Details"
                                            : `Show Technical Details (${relevantTags.length} tags)`}
                                        </Button>
                                        <Collapse in={expandedTags.has(processed.span.spanID)} animateOpacity>
                                          <Box
                                            mt={3}
                                            p={3}
                                            bg="gray.50"
                                            borderRadius="md"
                                            border="1px"
                                            borderColor="gray.200"
                                            boxShadow="sm"
                                          >
                                            <HStack spacing={2} mb={2} align="center">
                                              <Icon as={FiSettings} color="gray.600" boxSize={3} />
                                              <Text fontSize="xs" color="gray.700" fontWeight="semibold">
                                                Technical Information:
                                </Text>
                                            </HStack>

                                            <VStack spacing={2} align="stretch">
                                              {relevantTags.map((tag: { key: string; value: any }, tagIdx: number) => (
                                                <Box
                                                  key={tagIdx}
                                                  p={2}
                                                  bg="white"
                                                  borderRadius="sm"
                                                  border="1px"
                                                  borderColor="gray.200"
                                                >
                                                  <HStack spacing={2} align="start">
                                                    <Text
                                                      fontSize="xs"
                                                      color="gray.600"
                                                      fontWeight="medium"
                                                      minW="140px"
                                                      textTransform="uppercase"
                                                      letterSpacing="0.5px"
                                                    >
                                                      {tag.key}:
                                          </Text>
                                                    <Text
                                                      color="gray.800"
                                                      fontFamily="mono"
                                                      fontSize="xs"
                                                      wordBreak="break-word"
                                                      whiteSpace="pre-wrap"
                                                      flex={1}
                                                      maxH={tag.key.toLowerCase() === 'db.statement' ? "400px" : "none"}
                                                      overflowY={tag.key.toLowerCase() === 'db.statement' ? "auto" : "visible"}
                                                    >
                                                      {formatTagValue(tag.key, tag.value)}
                                              </Text>
                                          </HStack>
                                                </Box>
                                              ))}
                                            </VStack>

                                            {/* Internal child span (e.g., triton.inference) as a separate, indented "mini span card" */}
                                            {/* Keep it visually isolated from the parent tag list */}
                                            {processed.category === "phase.triton_inference" && (
                                              <Box mt={6} pt={4} borderTop="1px solid" borderTopColor="gray.200">
                                                <HStack spacing={2} mb={2} align="center">
                                                  <Icon as={FiLayers} color="gray.600" boxSize={3} />
                                                  <Text fontSize="xs" color="gray.700" fontWeight="semibold">
                                                    Internal child spans:
                                                  </Text>
                                                </HStack>

                                                {(spanRelationships.childSpans.get(processed.span.spanID) || [])
                                                  .map((childId: string) => spanRelationships.spanMap.get(childId))
                                                  .filter((s: any) => s && String(s.operationName).toLowerCase() === "triton.inference")
                                                  .map((s: any, i: number) => (
                                                    <Card
                                                      key={i}
                                                      bg="white"
                                                      border="1px"
                                                      borderColor="gray.200"
                                                      boxShadow="sm"
                                                      ml={6} // visual indent under parent span
                                                    >
                                                      <CardBody py={2}>
                                                        <HStack justify="space-between" align="center">
                                                          <HStack spacing={2} align="center">
                                                            <Text fontSize="sm" fontFamily="mono" color="gray.800" fontWeight="semibold">
                                                              {s.operationName}
                                                            </Text>
                                                          </HStack>
                                                          <Badge fontSize="xs" colorScheme="blue">
                                                            {formatDuration(s.duration)}
                                                          </Badge>
                                                        </HStack>

                                                        <Button
                                                          mt={2}
                                                          variant="outline"
                                                          colorScheme="gray"
                                                          width="full"
                                                          h="22px"
                                                          minH="22px"
                                                          maxH="22px"
                                                          fontSize="10px"
                                                          px={2}
                                                          py={0}
                                                          lineHeight="1.2"
                                                          leftIcon={<Icon as={expandedTags.has(s.spanID) ? FiEyeOff : FiEye} boxSize={2.5} />}
                                                          onClick={() => {
                                                            const spanId = s.spanID;
                                                            const newExpanded = new Set(expandedTags);
                                                            if (newExpanded.has(spanId)) newExpanded.delete(spanId);
                                                            else newExpanded.add(spanId);
                                                            setExpandedTags(newExpanded);
                                                          }}
                                                        >
                                                          {expandedTags.has(s.spanID)
                                                            ? "Hide Technical Details"
                                                            : `Show Technical Details (${(s.tags || []).length} tags)`}
                                                        </Button>

                                                        <Collapse in={expandedTags.has(s.spanID)} animateOpacity>
                                                          <Box mt={3} p={3} bg="gray.50" borderRadius="md" border="1px" borderColor="gray.200">
                                                            <VStack spacing={2} align="stretch">
                                                              {(s.tags || []).map((tag: { key: string; value: any }, tagIdx: number) => (
                                                                <Box
                                                                  key={tagIdx}
                                                                  p={2}
                                                                  bg="white"
                                                                  borderRadius="sm"
                                                                  border="1px"
                                                                  borderColor="gray.200"
                                                                >
                                                                  <HStack spacing={2} align="start">
                                                                    <Text
                                                                      fontSize="xs"
                                                                      color="gray.600"
                                                                      fontWeight="medium"
                                                                      minW="140px"
                                                                      textTransform="uppercase"
                                                                      letterSpacing="0.5px"
                                                                    >
                                                                      {tag.key}:
                                                                    </Text>
                                                                    <Text
                                                                      color="gray.800"
                                                                      fontFamily="mono"
                                                                      fontSize="xs"
                                                                      wordBreak="break-word"
                                                                      whiteSpace="pre-wrap"
                                                                      flex={1}
                                                                    >
                                                                      {formatTagValue(tag.key, tag.value)}
                                                                    </Text>
                                                                  </HStack>
                                                                </Box>
                                                              ))}
                                                            </VStack>
                                                          </Box>
                                                        </Collapse>
                                                      </CardBody>
                                                    </Card>
                                                  ))}
                                              </Box>
                                            )}
                                          </Box>
                                        </Collapse>
                                      </Box>
                                    )}
                                  </VStack>
                                </CardBody>
                              </Card>
                            );
                          })) : traceDetails?.spans && traceDetails.spans.length > 0 ? (
                            <Box>
                              <Text fontSize="sm" color="orange.600" textAlign="center" py={2} fontWeight="medium">
                                ⚠️ Spans found but not processed
                              </Text>
                              <Text fontSize="xs" color="gray.500" textAlign="center">
                                Check browser console for details. Total spans: {traceDetails.spans.length}
                              </Text>
                      </Box>
                    ) : (
                            <Text fontSize="sm" color="gray.500" textAlign="center" py={4}>
                              No processing steps available
                        </Text>
                          )}
                        </VStack>
                      </VStack>
                  </CardBody>
                </Card>
                </GridItem>
              </Grid>
            </VStack>
              ) : (
            <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" w="full">
                  <CardBody>
                <Flex direction="column" align="center" justify="center" py={12}>
                      <Text fontSize="lg" color="gray.500" fontWeight="medium" mb={2}>
                    No Trace Loaded
                      </Text>
                      <Text fontSize="sm" color="gray.400" textAlign="center">
                    Enter a trace ID above to view trace details
                      </Text>
                    </Flex>
                  </CardBody>
                </Card>
              )}
        </VStack>
      </ContentLayout>
    </>
  );
};

export default TracesPage;
