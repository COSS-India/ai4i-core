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
  Accordion,
  AccordionItem,
  AccordionButton,
  AccordionPanel,
  AccordionIcon,
  Alert,
  AlertIcon,
  AlertDescription,
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
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
  const [startTime, setStartTime] = useState<number | undefined>();
  const [endTime, setEndTime] = useState<number | undefined>();

  const cardBg = useColorModeValue("white", "gray.800");
  const borderColor = useColorModeValue("gray.200", "gray.700");

  // Set default time range (last 1 hour)
  useEffect(() => {
    if (!startTime && !endTime) {
      const now = Date.now();
      const oneHourAgo = now - 60 * 60 * 1000;
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
    queryKey: ["traces-search", service, operation, limit, startTime, endTime],
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

  const handleClear = () => {
    setService("");
    setOperation("");
    const now = Date.now();
    const oneHourAgo = now - 60 * 60 * 1000;
    setEndTime(now);
    setStartTime(oneHourAgo);
  };

  const formatDuration = (microseconds: number) => {
    if (microseconds < 1000) return `${microseconds}μs`;
    if (microseconds < 1000000) return `${(microseconds / 1000).toFixed(2)}ms`;
    return `${(microseconds / 1000000).toFixed(2)}s`;
  };

  const formatTimestamp = (microseconds: number) => {
    try {
      return new Date(microseconds / 1000).toLocaleString();
    } catch {
      return String(microseconds);
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
        <VStack spacing={6} align="stretch" w="full">
          <Heading size="lg">Traces Dashboard</Heading>

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
          <Card bg={cardBg} border="1px" borderColor={borderColor}>
            <CardBody>
              <HStack spacing={4} flexWrap="wrap">
                <FormControl minW="200px">
                  <FormLabel>Service</FormLabel>
                  <Select
                    placeholder="All Services"
                    value={service}
                    onChange={(e) => {
                      setService(e.target.value);
                      setOperation(""); // Reset operation when service changes
                    }}
                  >
                    {services?.map((svc) => (
                      <option key={svc} value={svc}>
                        {svc}
                      </option>
                    ))}
                  </Select>
                </FormControl>

                <FormControl minW="200px">
                  <FormLabel>Operation</FormLabel>
                  <Select
                    placeholder="All Operations"
                    value={operation}
                    onChange={(e) => setOperation(e.target.value)}
                    isDisabled={!service}
                  >
                    {operations?.map((op) => (
                      <option key={op} value={op}>
                        {op}
                      </option>
                    ))}
                  </Select>
                </FormControl>

                <FormControl minW="150px">
                  <FormLabel>Limit</FormLabel>
                  <Select
                    value={limit}
                    onChange={(e) => setLimit(Number(e.target.value))}
                  >
                    <option value={10}>10</option>
                    <option value={20}>20</option>
                    <option value={50}>50</option>
                    <option value={100}>100</option>
                  </Select>
                </FormControl>

                <FormControl minW="200px">
                  <FormLabel>Start Time</FormLabel>
                  <Input
                    type="datetime-local"
                    value={
                      startTime
                        ? new Date(startTime).toISOString().slice(0, 16)
                        : ""
                    }
                    onChange={(e) =>
                      setStartTime(new Date(e.target.value).getTime() * 1000)
                    }
                  />
                </FormControl>

                <FormControl minW="200px">
                  <FormLabel>End Time</FormLabel>
                  <Input
                    type="datetime-local"
                    value={
                      endTime
                        ? new Date(endTime).toISOString().slice(0, 16)
                        : ""
                    }
                    onChange={(e) =>
                      setEndTime(new Date(e.target.value).getTime() * 1000)
                    }
                  />
                </FormControl>
              </HStack>

              <HStack spacing={4} mt={4}>
                <Button
                  leftIcon={<SearchIcon />}
                  colorScheme="blue"
                  onClick={handleSearch}
                  isLoading={tracesLoading}
                >
                  Search
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

          {/* Traces Table */}
          <Card bg={cardBg} border="1px" borderColor={borderColor}>
            <CardBody>
              {tracesLoading ? (
                <Flex justify="center" align="center" py={8}>
                  <Spinner size="xl" />
                </Flex>
              ) : tracesData && tracesData.data.length > 0 ? (
                <>
                  <TableContainer>
                    <Table variant="simple" size="sm">
                      <Thead>
                        <Tr>
                          <Th>Trace ID</Th>
                          <Th>Service</Th>
                          <Th>Duration</Th>
                          <Th>Spans</Th>
                          <Th>Start Time</Th>
                          <Th>Actions</Th>
                        </Tr>
                      </Thead>
                      <Tbody>
                        {tracesData.data.map((trace: Trace) => (
                          <Tr
                            key={trace.traceID}
                            cursor="pointer"
                            _hover={{ bg: "gray.50" }}
                            onClick={() => setSelectedTraceId(trace.traceID)}
                          >
                            <Td>
                              <Text fontFamily="mono" fontSize="xs">
                                {trace.traceID.slice(0, 16)}...
                              </Text>
                            </Td>
                            <Td>{getServiceName(trace)}</Td>
                            <Td>
                              <Badge colorScheme="blue">
                                {formatDuration(trace.duration)}
                              </Badge>
                            </Td>
                            <Td>{trace.spans?.length || 0}</Td>
                            <Td>{formatTimestamp(trace.startTime)}</Td>
                            <Td>
                              <Button
                                size="xs"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setSelectedTraceId(trace.traceID);
                                }}
                              >
                                View Details
                              </Button>
                            </Td>
                          </Tr>
                        ))}
                      </Tbody>
                    </Table>
                  </TableContainer>

                  <Text mt={4} color="gray.500">
                    Showing {tracesData.data.length} of {tracesData.total || 0} traces
                  </Text>
                </>
              ) : (
                <Text textAlign="center" py={8} color="gray.500">
                  No traces found. Try adjusting your filters.
                </Text>
              )}
            </CardBody>
          </Card>

          {/* Trace Details */}
          {selectedTraceId && traceDetails && (
            <Card bg={cardBg} border="1px" borderColor={borderColor}>
              <CardBody>
                <Heading size="md" mb={4}>
                  Trace Details: {selectedTraceId.slice(0, 16)}...
                </Heading>

                {traceDetailsLoading ? (
                  <Flex justify="center" py={8}>
                    <Spinner />
                  </Flex>
                ) : (
                  <Accordion allowMultiple>
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
                          <Table size="sm">
                            <Thead>
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
                                  <Td>{span.operationName}</Td>
                                  <Td>{formatDuration(span.duration)}</Td>
                                  <Td>{formatTimestamp(span.startTime)}</Td>
                                  <Td>
                                    <HStack spacing={2} flexWrap="wrap">
                                      {span.tags?.slice(0, 3).map((tag, tagIdx) => (
                                        <Badge key={tagIdx} fontSize="xs">
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
                )}
              </CardBody>
            </Card>
          )}
        </VStack>
      </ContentLayout>
    </>
  );
};

export default TracesPage;

