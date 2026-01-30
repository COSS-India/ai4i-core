// Traces Dashboard - View and search traces from Jaeger

import {
  Box,
  Button,
  FormControl,
  FormLabel,
  Heading,
  HStack,
  Input,
  Select,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  TableContainer,
  Text,
  VStack,
  useToast,
  Badge,
  Spinner,
  Flex,
  IconButton,
  useColorModeValue,
  Card,
  CardBody,
  SimpleGrid,
  Grid,
  GridItem,
  Accordion,
  AccordionItem,
  AccordionButton,
  AccordionPanel,
  AccordionIcon,
  Alert,
  AlertIcon,
  AlertDescription,
  Divider,
} from "@chakra-ui/react";
import Head from "next/head";
import React, { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeftIcon, ChevronRightIcon, SearchIcon, RepeatIcon } from "@chakra-ui/icons";
import ContentLayout from "../components/common/ContentLayout";
import { useAuth } from "../hooks/useAuth";
import { useRouter } from "next/router";
import {
  searchTraces,
  getTraceById,
  getServicesWithTraces,
  getOperationsForService,
  Trace,
  TraceSearchResponse,
} from "../services/observabilityService";

const TracesPage: React.FC = () => {
  const toast = useToast();
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const [service, setService] = useState<string>("");
  const [operation, setOperation] = useState<string>("");
  const [limit, setLimit] = useState(20);
  const [page, setPage] = useState(1);
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
  const [startTime, setStartTime] = useState<number | undefined>();
  const [endTime, setEndTime] = useState<number | undefined>();
  const [traceIdSearch, setTraceIdSearch] = useState<string>("");

  const cardBg = useColorModeValue("white", "gray.800");
  const borderColor = useColorModeValue("gray.200", "gray.700");
  const theadBg = useColorModeValue("gray.50", "gray.700");
  const rowHoverBg = useColorModeValue("gray.50", "gray.800");

  // Set default time range (last 1 hour)
  useEffect(() => {
    if (!startTime && !endTime) {
      const now = Date.now() * 1000; // Convert to microseconds
      const oneHourAgo = now - (60 * 60 * 1000 * 1000); // 1 hour in microseconds
      setEndTime(now);
      setStartTime(oneHourAgo);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      toast({
        title: "Authentication Required",
        description: "Please log in to view traces.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      router.push("/auth");
    }
  }, [isAuthenticated, authLoading, router, toast]);

  // Fetch services list (only if authenticated)
  const { data: services, isLoading: servicesLoading, error: servicesError } = useQuery({
    queryKey: ["traces-services"],
    queryFn: getServicesWithTraces,
    enabled: isAuthenticated,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  // Handle services error
  useEffect(() => {
    if (servicesError && ((servicesError as any)?.response?.status === 401 || (servicesError as any)?.response?.status === 403)) {
      toast({
        title: "Authentication Required",
        description: "Please log in to view traces.",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      router.push("/auth");
    }
  }, [servicesError, router, toast]);

  // Fetch operations for selected service
  const { data: operations } = useQuery({
    queryKey: ["traces-operations", service],
    queryFn: () => getOperationsForService(service),
    enabled: !!service,
    staleTime: 5 * 60 * 1000,
  });

  // Fetch traces (only if authenticated)
  const {
    data: tracesData,
    isLoading: tracesLoading,
    refetch: refetchTraces,
    error: tracesError,
  } = useQuery({
    queryKey: ["traces-search", service, operation, limit, startTime, endTime, page],
    queryFn: () =>
      searchTraces({
        service: service || undefined,
        operation: operation || undefined,
        limit,
        start_time: startTime,
        end_time: endTime,
      }),
    enabled: isAuthenticated,
    staleTime: 30 * 1000, // 30 seconds
  });

  // Handle traces error
  useEffect(() => {
    if (tracesError && ((tracesError as any)?.response?.status === 401 || (tracesError as any)?.response?.status === 403)) {
      toast({
        title: "Authentication Required",
        description: "Please log in to view traces.",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      router.push("/auth");
    }
  }, [tracesError, router, toast]);

  // Fetch selected trace details
  const { data: traceDetails, isLoading: traceDetailsLoading } = useQuery({
    queryKey: ["trace-details", selectedTraceId],
    queryFn: () => getTraceById(selectedTraceId!),
    enabled: !!selectedTraceId,
    staleTime: 5 * 60 * 1000,
  });

  const handleSearch = () => {
    refetchTraces();
  };

  const handleSearchByTraceId = async () => {
    if (!traceIdSearch.trim()) {
      toast({
        title: "Trace ID Required",
        description: "Please enter a trace ID to search.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    try {
      // Fetch trace by ID
      const trace = await getTraceById(traceIdSearch.trim());
      // Set the selected trace ID to display it in the right panel
      setSelectedTraceId(trace.traceID);
      toast({
        title: "Trace Found",
        description: `Successfully loaded trace ${trace.traceID.slice(0, 16)}...`,
        status: "success",
        duration: 3000,
        isClosable: true,
      });
    } catch (error: any) {
      toast({
        title: "Trace Not Found",
        description: error?.message || "Could not find trace with the provided ID.",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    }
  };

  const handleClear = () => {
    setService("");
    setOperation("");
    setPage(1);
    setTraceIdSearch("");
    setSelectedTraceId(null);
    const now = Date.now() * 1000; // Convert to microseconds
    const oneHourAgo = now - (60 * 60 * 1000 * 1000); // 1 hour in microseconds
    setEndTime(now);
    setStartTime(oneHourAgo);
  };

  const formatDuration = (microseconds: number | undefined) => {
    if (!microseconds || isNaN(microseconds)) return "N/A";
    if (microseconds < 1000) return `${microseconds}μs`;
    if (microseconds < 1000000) return `${(microseconds / 1000).toFixed(2)}ms`;
    return `${(microseconds / 1000000).toFixed(2)}s`;
  };

  const formatTimestamp = (microseconds: number | undefined) => {
    if (!microseconds || isNaN(microseconds)) return "N/A";
    try {
      // Convert microseconds to milliseconds for Date constructor
      const milliseconds = microseconds / 1000;
      const date = new Date(milliseconds);
      if (isNaN(date.getTime())) return "Invalid Date";
      return date.toLocaleString();
    } catch {
      return "Invalid Date";
    }
  };

  const getServiceName = (trace: Trace) => {
    if (trace.processes && Object.keys(trace.processes).length > 0) {
      const firstProcess = Object.values(trace.processes)[0];
      return firstProcess.serviceName || "Unknown";
    }
    return "Unknown";
  };

  return (
    <>
      <Head>
        <title>Traces Dashboard - AI4Inclusion Console</title>
        <meta name="description" content="View and search traces from Jaeger" />
      </Head>

      <ContentLayout>
        <VStack spacing={6} w="full" align="stretch">
          {/* Page Header */}
          <Box textAlign="center" mb={2}>
            <Heading size="lg" color="gray.800" mb={1}>
              Traces Dashboard
            </Heading>
            <Text color="gray.600" fontSize="sm">
              View and search traces from Jaeger
            </Text>
          </Box>

          {/* Show auth warning if not authenticated */}
          {!authLoading && !isAuthenticated && (
            <Alert status="warning">
              <AlertIcon />
              <AlertDescription>
                Please log in to view traces. <Button
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

          {/* Show auth error if query failed due to auth */}
          {tracesError && (tracesError as any)?.response?.status === 403 && (
            <Alert status="error">
              <AlertIcon />
              <AlertDescription>
                Authentication failed. Please log in again.
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

          {/* Filters */}
          <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" w="full">
            <CardBody>
              <Heading size="sm" mb={4} color="gray.700">Filters</Heading>
              <SimpleGrid columns={{ base: 1, md: 3 }} spacing={4} w="full">
                <FormControl gridColumn={{ base: "1", md: "span 3" }}>
                  <FormLabel fontWeight="medium" color="gray.700">Search by Trace ID</FormLabel>
                  <HStack spacing={2}>
                    <Input
                      placeholder="Enter trace ID (e.g., 2fa9c938156e0e52b96ee48b369e19db)..."
                      value={traceIdSearch}
                      onChange={(e) => setTraceIdSearch(e.target.value)}
                      bg="white"
                      fontFamily="mono"
                      fontSize="sm"
                      onKeyPress={(e) => {
                        if (e.key === "Enter") {
                          handleSearchByTraceId();
                        }
                      }}
                    />
                    <Button
                      colorScheme="orange"
                      onClick={handleSearchByTraceId}
                      isDisabled={!traceIdSearch.trim()}
                      leftIcon={<SearchIcon />}
                    >
                      Search
                    </Button>
                  </HStack>
                </FormControl>

                <FormControl>
                  <FormLabel fontWeight="medium" color="gray.700">Service</FormLabel>
                  <Select
                    placeholder={servicesLoading ? "Loading services..." : "All Services"}
                    value={service}
                    onChange={(e) => {
                      setService(e.target.value);
                      setOperation(""); // Reset operation when service changes
                      setPage(1); // Reset to first page
                    }}
                    bg="white"
                    isDisabled={servicesLoading}
                  >
                    {servicesLoading ? (
                      <option value="" disabled>Loading services...</option>
                    ) : services && Array.isArray(services) && services.length > 0 ? (
                      services.map((svc) => (
                        <option key={svc} value={svc}>
                          {svc}
                        </option>
                      ))
                    ) : (
                      <option value="" disabled>No services available</option>
                    )}
                  </Select>
                </FormControl>

                <FormControl>
                  <FormLabel fontWeight="medium" color="gray.700">Operation</FormLabel>
                  <Select
                    placeholder="All Operations"
                    value={operation}
                    onChange={(e) => {
                      setOperation(e.target.value);
                      setPage(1); // Reset to first page
                    }}
                    isDisabled={!service}
                    bg="white"
                  >
                    {operations && Array.isArray(operations) && operations.length > 0 ? (
                      operations.map((op) => (
                        <option key={op} value={op}>
                          {op}
                        </option>
                      ))
                    ) : (
                      <option value="" disabled>No operations available</option>
                    )}
                  </Select>
                </FormControl>

                <FormControl>
                  <FormLabel fontWeight="medium" color="gray.700">Limit</FormLabel>
                  <Select
                    value={limit}
                    onChange={(e) => {
                      setLimit(Number(e.target.value));
                      setPage(1); // Reset to first page
                    }}
                    bg="white"
                  >
                    <option value={10}>10</option>
                    <option value={20}>20</option>
                    <option value={50}>50</option>
                    <option value={100}>100</option>
                  </Select>
                </FormControl>

                <FormControl>
                  <FormLabel fontWeight="medium" color="gray.700">Start Time</FormLabel>
                  <Input
                    type="datetime-local"
                    value={
                      startTime
                        ? new Date(startTime / 1000).toISOString().slice(0, 16) // Convert from microseconds to milliseconds
                        : ""
                    }
                    onChange={(e) => {
                      setStartTime(new Date(e.target.value).getTime() * 1000); // Convert to microseconds
                      setPage(1); // Reset to first page
                    }}
                    bg="white"
                  />
                </FormControl>

                <FormControl>
                  <FormLabel fontWeight="medium" color="gray.700">End Time</FormLabel>
                  <Input
                    type="datetime-local"
                    value={
                      endTime
                        ? new Date(endTime / 1000).toISOString().slice(0, 16) // Convert from microseconds to milliseconds
                        : ""
                    }
                    onChange={(e) => {
                      setEndTime(new Date(e.target.value).getTime() * 1000); // Convert to microseconds
                      setPage(1); // Reset to first page
                    }}
                    bg="white"
                  />
                </FormControl>
              </SimpleGrid>

              <HStack spacing={4} mt={4} justify="flex-end">
                <Button
                  leftIcon={<SearchIcon />}
                  colorScheme="orange"
                  onClick={handleSearchByTraceId}
                  isDisabled={!traceIdSearch.trim()}
                >
                  Search by Trace ID
                </Button>
                <Button
                  leftIcon={<SearchIcon />}
                  colorScheme="blue"
                  onClick={handleSearch}
                  isLoading={tracesLoading}
                >
                  Search Traces
                </Button>
                <Button variant="outline" onClick={handleClear}>
                  Clear
                </Button>
                <IconButton
                  aria-label="Refresh"
                  icon={<RepeatIcon />}
                  onClick={() => refetchTraces()}
                  isLoading={tracesLoading}
                />
              </HStack>
            </CardBody>
          </Card>

          {/* Split View: Traces List (Left) and Trace Details (Right) */}
          <Grid templateColumns={{ base: "1fr", lg: "1fr 1fr" }} gap={4} w="full">
            {/* Left Side: Traces List */}
            <GridItem>
              <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" w="full" h="full">
                <CardBody p={0}>
                  <Box p={4} borderBottom="1px" borderColor={borderColor}>
                    <Heading size="sm" color="gray.700">Traces List</Heading>
                    <Text fontSize="xs" color="gray.500" mt={1}>
                      {tracesData && tracesData.data ? `${tracesData.data.length} traces` : "Loading..."}
                    </Text>
                  </Box>
                  {tracesLoading ? (
                    <Flex justify="center" align="center" py={8}>
                      <Spinner size="xl" />
                      <Text ml={4}>Loading traces...</Text>
                    </Flex>
                  ) : tracesData && tracesData.data && Array.isArray(tracesData.data) && tracesData.data.length > 0 ? (
                    <Box overflowY="auto" maxH="calc(100vh - 400px)">
                      <VStack spacing={0} align="stretch">
                        {tracesData.data.map((trace: Trace) => (
                          <Box
                            key={trace.traceID}
                            p={3}
                            cursor="pointer"
                            bg={selectedTraceId === trace.traceID ? "blue.50" : "transparent"}
                            borderLeft={selectedTraceId === trace.traceID ? "3px solid" : "3px solid transparent"}
                            borderLeftColor={selectedTraceId === trace.traceID ? "blue.500" : "transparent"}
                            _hover={{ bg: rowHoverBg }}
                            transition="all 0.2s"
                            onClick={() => setSelectedTraceId(trace.traceID)}
                          >
                            <HStack justify="space-between" align="start">
                              <VStack align="start" spacing={1} flex={1}>
                                <Text fontFamily="mono" fontSize="xs" color="gray.600" fontWeight="medium">
                                  {trace.traceID?.slice(0, 16) || "N/A"}...
                                </Text>
                                <Text fontSize="sm" fontWeight="medium" color="gray.700">
                                  {getServiceName(trace)}
                                </Text>
                                <HStack spacing={2}>
                                  <Badge colorScheme="blue" fontSize="xs" px={2} py={0.5} borderRadius="md">
                                    {formatDuration(trace.duration)}
                                  </Badge>
                                  <Text fontSize="xs" color="gray.500">
                                    {trace.spans?.length || 0} spans
                                  </Text>
                                </HStack>
                                <Text fontSize="xs" color="gray.500">
                                  {formatTimestamp(trace.startTime)}
                                </Text>
                              </VStack>
                            </HStack>
                          </Box>
                        ))}
                      </VStack>
                    </Box>
                  ) : tracesData && tracesData.total === 0 ? (
                    <VStack spacing={2} py={8}>
                      <Text textAlign="center" color="gray.500" fontWeight="medium">
                        No traces found for the selected filters.
                      </Text>
                      <Text fontSize="sm" color="gray.400">
                        Total: {tracesData.total || 0} traces. Try adjusting the time range or removing filters.
                      </Text>
                      <HStack spacing={2} justify="center" mt={2}>
                        <Button size="xs" variant="outline" onClick={handleClear}>
                          Clear Filters
                        </Button>
                        <Button size="xs" variant="outline" onClick={() => refetchTraces()}>
                          Refresh
                        </Button>
                      </HStack>
                    </VStack>
                  ) : (
                    <VStack spacing={2} py={8}>
                      <Text textAlign="center" color="gray.500">
                        {tracesData ? 'No traces data available.' : 'Waiting for data...'}
                      </Text>
                      {isAuthenticated && (
                        <>
                          <Text fontSize="sm" color="gray.400" textAlign="center">
                            Make sure Jaeger has traces indexed and your time range includes trace entries.
                          </Text>
                          <Button size="sm" variant="outline" onClick={() => refetchTraces()}>
                            Refresh
                          </Button>
                        </>
                      )}
                    </VStack>
                  )}
                  {/* Pagination for Left Side */}
                  {tracesData && tracesData.data && Array.isArray(tracesData.data) && tracesData.data.length > 0 && (
                    <Box p={3} borderTop="1px" borderColor={borderColor} bg={theadBg}>
                      <Flex justify="space-between" align="center" w="full">
                        <Text fontSize="xs" color="gray.600" fontWeight="medium">
                          Showing {tracesData.data.length} of {tracesData.total?.toLocaleString() || tracesData.data.length}
                        </Text>
                        {tracesData.total && tracesData.total > limit && (
                          <HStack spacing={1}>
                            <IconButton
                              aria-label="Previous page"
                              icon={<ChevronLeftIcon />}
                              onClick={() => {
                                setPage((p) => Math.max(1, p - 1));
                                refetchTraces();
                              }}
                              isDisabled={page === 1}
                              size="xs"
                              variant="outline"
                            />
                            <Text fontSize="xs" fontWeight="bold" color="gray.700" minW="20px" textAlign="center">
                              {page}
                            </Text>
                            <IconButton
                              aria-label="Next page"
                              icon={<ChevronRightIcon />}
                              onClick={() => {
                                setPage((p) => p + 1);
                                refetchTraces();
                              }}
                              isDisabled={tracesData.data.length < limit}
                              size="xs"
                              variant="outline"
                            />
                          </HStack>
                        )}
                      </Flex>
                    </Box>
                  )}
                </CardBody>
              </Card>
            </GridItem>

            {/* Right Side: Trace Details */}
            <GridItem>
              {selectedTraceId ? (
                <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" w="full" h="full">
                  <CardBody>
                    <Box mb={4}>
                      <Heading size="md" mb={2}>
                        Trace Details
                      </Heading>
                      <Text fontFamily="mono" fontSize="sm" color="gray.600">
                        {selectedTraceId}
                      </Text>
                    </Box>

                    {traceDetailsLoading ? (
                      <Flex justify="center" align="center" py={8}>
                        <Spinner size="xl" />
                        <Text ml={4}>Loading trace details...</Text>
                      </Flex>
                    ) : traceDetails ? (
                      <Box>
                        {/* Trace Summary */}
                        <Box mb={4} p={3} bg={theadBg} borderRadius="md">
                          <SimpleGrid columns={2} spacing={4}>
                            <Box>
                              <Text fontSize="xs" color="gray.500" mb={1}>Service</Text>
                              <Text fontSize="sm" fontWeight="medium" color="gray.700">
                                {getServiceName(traceDetails)}
                              </Text>
                            </Box>
                            <Box>
                              <Text fontSize="xs" color="gray.500" mb={1}>Duration</Text>
                              <Text fontSize="sm" fontWeight="medium" color="gray.700">
                                {formatDuration(traceDetails.duration)}
                              </Text>
                            </Box>
                            <Box>
                              <Text fontSize="xs" color="gray.500" mb={1}>Total Spans</Text>
                              <Text fontSize="sm" fontWeight="medium" color="gray.700">
                                {traceDetails.spans?.length || 0}
                              </Text>
                            </Box>
                            <Box>
                              <Text fontSize="xs" color="gray.500" mb={1}>Start Time</Text>
                              <Text fontSize="sm" fontWeight="medium" color="gray.700">
                                {formatTimestamp(traceDetails.startTime)}
                              </Text>
                            </Box>
                          </SimpleGrid>
                        </Box>

                        <Divider my={4} />

                        {/* Spans */}
                        <Accordion allowMultiple defaultIndex={[0]}>
                          <AccordionItem>
                            <AccordionButton>
                              <Box flex="1" textAlign="left">
                                <Text fontWeight="bold">
                                  Spans ({traceDetails.spans?.length || 0})
                                </Text>
                              </Box>
                              <AccordionIcon />
                            </AccordionButton>
                            <AccordionPanel pb={4}>
                              <TableContainer>
                                <Table size="sm" variant="simple">
                                  <Thead bg={theadBg}>
                                    <Tr>
                                      <Th>Operation</Th>
                                      <Th>Duration</Th>
                                      <Th>Start Time</Th>
                                      <Th>Tags</Th>
                                    </Tr>
                                  </Thead>
                                  <Tbody>
                                    {traceDetails.spans?.map((span, idx) => (
                                      <Tr key={idx}>
                                        <Td>
                                          <Text fontSize="sm" fontFamily="mono">
                                            {span.operationName}
                                          </Text>
                                        </Td>
                                        <Td>
                                          <Badge colorScheme="blue" fontSize="xs">
                                            {formatDuration(span.duration)}
                                          </Badge>
                                        </Td>
                                        <Td fontSize="xs" color="gray.600">
                                          {formatTimestamp(span.startTime)}
                                        </Td>
                                        <Td>
                                          <HStack spacing={2} flexWrap="wrap">
                                            {span.tags?.slice(0, 3).map((tag, tagIdx) => (
                                              <Badge key={tagIdx} fontSize="xs" colorScheme="gray">
                                                {tag.key}: {String(tag.value)}
                                              </Badge>
                                            ))}
                                            {span.tags && span.tags.length > 3 && (
                                              <Text fontSize="xs" color="gray.500">
                                                +{span.tags.length - 3} more
                                              </Text>
                                            )}
                                          </HStack>
                                        </Td>
                                      </Tr>
                                    ))}
                                  </Tbody>
                                </Table>
                              </TableContainer>
                            </AccordionPanel>
                          </AccordionItem>
                        </Accordion>
                      </Box>
                    ) : (
                      <VStack spacing={2} py={8}>
                        <Text textAlign="center" color="gray.500">
                          Failed to load trace details.
                        </Text>
                        <Button size="sm" variant="outline" onClick={() => {
                          if (selectedTraceId) {
                            // Trigger refetch
                            setSelectedTraceId(null);
                            setTimeout(() => setSelectedTraceId(selectedTraceId), 100);
                          }
                        }}>
                          Retry
                        </Button>
                      </VStack>
                    )}
                  </CardBody>
                </Card>
              ) : (
                <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" w="full" h="full">
                  <CardBody>
                    <Flex direction="column" align="center" justify="center" h="full" py={12}>
                      <Text fontSize="lg" color="gray.500" fontWeight="medium" mb={2}>
                        No Trace Selected
                      </Text>
                      <Text fontSize="sm" color="gray.400" textAlign="center">
                        Click on a trace from the list to view its details
                      </Text>
                    </Flex>
                  </CardBody>
                </Card>
              )}
            </GridItem>
          </Grid>
        </VStack>
      </ContentLayout>
    </>
  );
};

export default TracesPage;

