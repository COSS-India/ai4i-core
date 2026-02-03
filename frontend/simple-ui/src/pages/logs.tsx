// Logs Dashboard - View and search logs from OpenSearch

import {
  Box,
  Button,
  FormControl,
  FormLabel,
  Heading,
  HStack,
  Input,
  Link,
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
  Stat,
  StatLabel,
  StatNumber,
  StatHelpText,
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
import { getJwtToken } from "../services/api";
import {
  searchLogs,
  getLogAggregations,
  getServicesWithLogs,
  LogEntry,
  LogSearchResponse,
  LogAggregationResponse,
} from "../services/observabilityService";

const LogsPage: React.FC = () => {
  const toast = useToast();
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(50);
  const [service, setService] = useState<string>("");
  const [level, setLevel] = useState<string>("");
  const [searchText, setSearchText] = useState<string>("");
  const [startTime, setStartTime] = useState<string>("");
  const [endTime, setEndTime] = useState<string>("");
  
  const cardBg = useColorModeValue("white", "gray.800");
  const borderColor = useColorModeValue("gray.200", "gray.700");
  const theadBg = useColorModeValue("gray.50", "gray.700");
  const rowHoverBg = useColorModeValue("gray.50", "gray.800");

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      toast({
        title: "Authentication Required",
        description: "Please log in to view logs.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      router.push("/auth");
    }
  }, [isAuthenticated, authLoading, router, toast]);

  // Fetch services list (only if authenticated)
  const { data: services, isLoading: servicesLoading, error: servicesError } = useQuery({
    queryKey: ["logs-services"],
    queryFn: getServicesWithLogs,
    enabled: isAuthenticated,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  // Handle services error
  useEffect(() => {
    if (servicesError && (servicesError as any)?.response?.status === 401 || (servicesError as any)?.response?.status === 403) {
      toast({
        title: "Authentication Required",
        description: "Please log in to view logs.",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      router.push("/auth");
    }
  }, [servicesError, router, toast]);

  // Fetch aggregations (only if authenticated)
  const { data: aggregations, isLoading: aggregationsLoading, error: aggregationsError } = useQuery({
    queryKey: ["logs-aggregations", startTime, endTime],
    queryFn: () =>
      getLogAggregations({
        start_time: startTime || undefined,
        end_time: endTime || undefined,
      }),
    enabled: isAuthenticated,
    staleTime: 1 * 60 * 1000, // 1 minute
  });

  // Handle aggregations error
  useEffect(() => {
    if (aggregationsError && ((aggregationsError as any)?.response?.status === 401 || (aggregationsError as any)?.response?.status === 403)) {
      toast({
        title: "Authentication Required",
        description: "Please log in to view logs.",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    }
  }, [aggregationsError, toast]);

  // Fetch logs (only if authenticated)
  const {
    data: logsData,
    isLoading: logsLoading,
    refetch: refetchLogs,
    error: logsError,
  } = useQuery({
    queryKey: [
      "logs-search",
      page,
      size,
      service,
      level,
      searchText,
      startTime,
      endTime,
    ],
    queryFn: async () => {
      const result = await searchLogs({
        page,
        size,
        service: service || undefined,
        level: level || undefined,
        search_text: searchText || undefined,
        start_time: startTime || undefined,
        end_time: endTime || undefined,
      });
      // Ensure logs is always an array
      if (result && !Array.isArray(result.logs)) {
        console.warn('API returned non-array logs, converting:', result);
        result.logs = [];
      }
      return result;
    },
    enabled: isAuthenticated,
    staleTime: 30 * 1000, // 30 seconds
  });

  // Handle logs error
  useEffect(() => {
    if (logsError) {
      const error = logsError as any;
      console.error('Logs query error:', {
        status: error?.response?.status,
        statusText: error?.response?.statusText,
        data: error?.response?.data,
        message: error?.message,
        url: error?.config?.url,
      });
      
      if (error?.response?.status === 401) {
        // 401 Unauthorized - redirect to login
        toast({
          title: "Authentication Required",
          description: error?.response?.data?.detail || "Please log in to view logs.",
          status: "error",
          duration: 5000,
          isClosable: true,
        });
        router.push("/auth");
      } else if (error?.response?.status === 403) {
        // 403 Forbidden - show error message (user is authenticated but lacks permission)
        let errorMessage = 'Access denied. You must be associated with a tenant to access logs.';
        if (error?.response?.data?.detail) {
          const detail = error.response.data.detail;
          if (typeof detail === 'string') {
            errorMessage = detail;
          } else if (typeof detail === 'object') {
            errorMessage = detail.message || detail.detail || JSON.stringify(detail);
          } else {
            errorMessage = String(detail);
          }
        }
        toast({
          title: "Access Denied",
          description: errorMessage,
          status: "error",
          duration: 8000,
          isClosable: true,
        });
      } else {
        // Show other errors as toast
        let errorMessage = 'Failed to load logs';
        if (error?.response?.data?.detail) {
          const detail = error.response.data.detail;
          if (typeof detail === 'string') {
            errorMessage = detail;
          } else if (typeof detail === 'object') {
            // Handle structured error response
            errorMessage = detail.message || detail.detail || JSON.stringify(detail);
          } else {
            errorMessage = String(detail);
          }
        } else if (error?.message) {
          errorMessage = error.message;
        }
        toast({
          title: "Error Loading Logs",
          description: errorMessage,
          status: "error",
          duration: 5000,
          isClosable: true,
        });
      }
    }
  }, [logsError, router, toast]);

  // Debug: Log successful responses
  useEffect(() => {
    if (logsData) {
      console.log('Logs data received:', {
        total: logsData.total,
        logsCount: Array.isArray(logsData.logs) ? logsData.logs.length : 0,
        logsType: typeof logsData.logs,
        isArray: Array.isArray(logsData.logs),
        page: logsData.page,
        total_pages: logsData.total_pages,
        hasLogs: !!logsData.logs,
        sampleLog: Array.isArray(logsData.logs) ? logsData.logs[0] : null,
        fullData: JSON.stringify(logsData).substring(0, 500),
      });
    }
    if (services) {
      console.log('Services data received:', {
        servicesCount: Array.isArray(services) ? services.length : 0,
        servicesType: typeof services,
        isArray: Array.isArray(services),
        services: services,
      });
    }
  }, [logsData, services]);

  // Debug: Log authentication state
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const localToken = localStorage.getItem('access_token');
      const sessionToken = sessionStorage.getItem('access_token');
      const token = localToken || sessionToken;
      console.log('Logs page auth state:', {
        isAuthenticated,
        authLoading,
        hasLocalToken: !!localToken,
        hasSessionToken: !!sessionToken,
        hasToken: !!token,
        tokenLength: token?.length || 0,
        tokenPreview: token ? `${token.substring(0, 20)}...` : 'none',
      });
      
      // Also check what getJwtToken returns
      const jwtFromApi = getJwtToken();
      console.log('getJwtToken() result:', {
        hasToken: !!jwtFromApi,
        tokenLength: jwtFromApi?.length || 0,
      });
    }
  }, [isAuthenticated, authLoading]);

  // Set default time range (last 1 hour)
  useEffect(() => {
    if (!startTime && !endTime) {
      const now = new Date();
      const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);
      setEndTime(now.toISOString().slice(0, 16));
      setStartTime(oneHourAgo.toISOString().slice(0, 16));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSearch = () => {
    setPage(1);
    refetchLogs();
  };

  const handleClear = () => {
    setService("");
    setLevel("");
    setSearchText("");
    const now = new Date();
    const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);
    setEndTime(now.toISOString().slice(0, 16));
    setStartTime(oneHourAgo.toISOString().slice(0, 16));
    setPage(1);
  };

  const getLevelColor = (level: string) => {
    const levelUpper = level.toUpperCase();
    if (levelUpper === "ERROR") return "red";
    if (levelUpper === "WARN" || levelUpper === "WARNING") return "orange";
    if (levelUpper === "INFO") return "blue";
    if (levelUpper === "DEBUG") return "gray";
    return "gray";
  };

  const formatTimestamp = (timestamp: string) => {
    try {
      return new Date(timestamp).toLocaleString();
    } catch {
      return timestamp;
    }
  };

  return (
    <>
      <Head>
        <title>Logs Dashboard - AI4Inclusion Console</title>
        <meta name="description" content="View and search logs from OpenSearch" />
      </Head>

      <ContentLayout>
        <VStack spacing={6} w="full" align="stretch">
          {/* Page Header */}
          <Box textAlign="center" mb={2}>
            <Heading size="lg" color="gray.800" mb={1}>
              Logs Dashboard
            </Heading>
            <Text color="gray.600" fontSize="sm">
              View and search logs from OpenSearch
            </Text>
          </Box>

          {/* Show auth warning if not authenticated */}
          {!authLoading && !isAuthenticated && (
            <Alert status="warning">
              <AlertIcon />
              <AlertDescription>
                Please log in to view logs. <Button
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

          {/* Show token debug info in development */}
          {process.env.NODE_ENV === 'development' && isAuthenticated && typeof window !== 'undefined' && (
            <Alert status="info" fontSize="xs">
              <AlertIcon />
              <AlertDescription>
                <Text fontSize="xs">
                  Debug: Auth={isAuthenticated ? '✅' : '❌'} | 
                  Token={getJwtToken() ? `✅ (${getJwtToken()?.length || 0})` : '❌'} |
                  Local={localStorage.getItem('access_token') ? '✅' : '❌'} | 
                  Session={sessionStorage.getItem('access_token') ? '✅' : '❌'}
                </Text>
              </AlertDescription>
            </Alert>
          )}

          {/* Show error messages */}
          {logsError && (
            <Alert status="error">
              <AlertIcon />
              <AlertDescription>
                {(() => {
                  const error = logsError as any;
                  if (error?.response?.status === 401) {
                    return (
                      <>
                        Authentication failed. Please log in again.
                        <Button
                          size="sm"
                          colorScheme="blue"
                          ml={4}
                          onClick={() => router.push("/auth")}
                        >
                          Log In
                        </Button>
                      </>
                    );
                  } else if (error?.response?.status === 403) {
                    // 403 Forbidden - show permission error
                    let errorMsg = 'Access denied. You must be associated with a tenant to access logs.';
                    if (error?.response?.data?.detail) {
                      const detail = error.response.data.detail;
                      if (typeof detail === 'string') {
                        errorMsg = detail;
                      } else if (typeof detail === 'object') {
                        errorMsg = detail.message || detail.detail || JSON.stringify(detail);
                      } else {
                        errorMsg = String(detail);
                      }
                    }
                    return errorMsg;
                  }
                  let errorMsg = 'Unknown error';
                  if (error?.response?.data?.detail) {
                    const detail = error.response.data.detail;
                    if (typeof detail === 'string') {
                      errorMsg = detail;
                    } else if (typeof detail === 'object') {
                      errorMsg = detail.message || detail.detail || JSON.stringify(detail);
                    } else {
                      errorMsg = String(detail);
                    }
                  } else if (error?.message) {
                    errorMsg = error.message;
                  }
                  return `Error loading logs: ${errorMsg}`;
                })()}
              </AlertDescription>
            </Alert>
          )}

          {servicesError && !servicesLoading && (
            <Alert status="warning">
              <AlertIcon />
              <AlertDescription>
                Failed to load services: {(() => {
                  const error = servicesError as any;
                  if (error?.response?.data?.detail) {
                    const detail = error.response.data.detail;
                    if (typeof detail === 'string') return detail;
                    if (typeof detail === 'object') return detail.message || detail.detail || JSON.stringify(detail);
                    return String(detail);
                  }
                  return error?.message || 'Unknown error';
                })()}
              </AlertDescription>
            </Alert>
          )}

          {aggregationsError && !aggregationsLoading && (
            <Alert status="warning">
              <AlertIcon />
              <AlertDescription>
                Failed to load aggregations: {(() => {
                  const error = aggregationsError as any;
                  if (error?.response?.data?.detail) {
                    const detail = error.response.data.detail;
                    if (typeof detail === 'string') return detail;
                    if (typeof detail === 'object') return detail.message || detail.detail || JSON.stringify(detail);
                    return String(detail);
                  }
                  return error?.message || 'Unknown error';
                })()}
              </AlertDescription>
            </Alert>
          )}

          {/* Aggregations */}
          {aggregations && (
            <SimpleGrid columns={{ base: 2, md: 4 }} spacing={4}>
              <Card 
                bg={cardBg} 
                border="1px" 
                borderColor={borderColor}
                boxShadow="sm"
                _hover={{ boxShadow: "md", transform: "translateY(-2px)" }}
                transition="all 0.2s"
              >
                <CardBody>
                  <Stat>
                    <StatLabel fontSize="sm" color="gray.600" fontWeight="medium">Total Logs</StatLabel>
                    <StatNumber fontSize="2xl" fontWeight="bold" color="gray.800">
                      {aggregations.total?.toLocaleString() || 0}
                    </StatNumber>
                  </Stat>
                </CardBody>
              </Card>
              <Card 
                bg={cardBg} 
                border="1px" 
                borderColor="red.200"
                boxShadow="sm"
                _hover={{ boxShadow: "md", transform: "translateY(-2px)", borderColor: "red.300" }}
                transition="all 0.2s"
              >
                <CardBody>
                  <Stat>
                    <StatLabel fontSize="sm" color="gray.600" fontWeight="medium">Errors</StatLabel>
                    <StatNumber fontSize="2xl" fontWeight="bold" color="red.500">
                      {aggregations.error_count?.toLocaleString() || 0}
                    </StatNumber>
                  </Stat>
                </CardBody>
              </Card>
              <Card 
                bg={cardBg} 
                border="1px" 
                borderColor="orange.200"
                boxShadow="sm"
                _hover={{ boxShadow: "md", transform: "translateY(-2px)", borderColor: "orange.300" }}
                transition="all 0.2s"
              >
                <CardBody>
                  <Stat>
                    <StatLabel fontSize="sm" color="gray.600" fontWeight="medium">Warnings</StatLabel>
                    <StatNumber fontSize="2xl" fontWeight="bold" color="orange.500">
                      {aggregations.warning_count?.toLocaleString() || 0}
                    </StatNumber>
                  </Stat>
                </CardBody>
              </Card>
              <Card 
                bg={cardBg} 
                border="1px" 
                borderColor="blue.200"
                boxShadow="sm"
                _hover={{ boxShadow: "md", transform: "translateY(-2px)", borderColor: "blue.300" }}
                transition="all 0.2s"
              >
                <CardBody>
                  <Stat>
                    <StatLabel fontSize="sm" color="gray.600" fontWeight="medium">Info</StatLabel>
                    <StatNumber fontSize="2xl" fontWeight="bold" color="blue.500">
                      {(aggregations.by_level?.INFO || aggregations.info_count || 0).toLocaleString()}
                    </StatNumber>
                  </Stat>
                </CardBody>
              </Card>
            </SimpleGrid>
          )}

          {/* Filters */}
          <Card 
            bg={cardBg} 
            border="1px" 
            borderColor={borderColor}
            boxShadow="sm"
            w="full"
          >
            <CardBody>
              <Heading size="sm" mb={4} color="gray.700">Filters</Heading>
              <SimpleGrid columns={{ base: 1, md: 3 }} spacing={4} w="full">
                <FormControl>
                  <FormLabel fontWeight="medium">Service</FormLabel>
                  <Select
                    placeholder="All Services"
                    value={service}
                    onChange={(e) => setService(e.target.value)}
                    bg="white"
                  >
                    {Array.isArray(services) && services.map((svc) => (
                      <option key={svc} value={svc}>
                        {svc}
                      </option>
                    ))}
                  </Select>
                </FormControl>

                <FormControl>
                  <FormLabel fontWeight="medium">Level</FormLabel>
                  <Select
                    placeholder="All Levels"
                    value={level}
                    onChange={(e) => setLevel(e.target.value)}
                    bg="white"
                  >
                    <option value="ERROR">ERROR</option>
                    <option value="WARN">WARN</option>
                    <option value="INFO">INFO</option>
                    <option value="DEBUG">DEBUG</option>
                  </Select>
                </FormControl>

                <FormControl>
                  <FormLabel fontWeight="medium">Search Text</FormLabel>
                  <Input
                    placeholder="Search in log messages..."
                    value={searchText}
                    onChange={(e) => setSearchText(e.target.value)}
                    onKeyPress={(e) => {
                      if (e.key === "Enter") handleSearch();
                    }}
                    bg="white"
                  />
                </FormControl>

                <FormControl>
                  <FormLabel fontWeight="medium">Start Time</FormLabel>
                  <Input
                    type="datetime-local"
                    value={startTime}
                    onChange={(e) => setStartTime(e.target.value)}
                    bg="white"
                  />
                </FormControl>

                <FormControl>
                  <FormLabel fontWeight="medium">End Time</FormLabel>
                  <Input
                    type="datetime-local"
                    value={endTime}
                    onChange={(e) => setEndTime(e.target.value)}
                    bg="white"
                  />
                </FormControl>

                <FormControl>
                  <FormLabel fontWeight="medium">Page Size</FormLabel>
                  <Select
                    value={size}
                    onChange={(e) => {
                      setSize(Number(e.target.value));
                      setPage(1);
                    }}
                    bg="white"
                  >
                    <option value={25}>25</option>
                    <option value={50}>50</option>
                    <option value={100}>100</option>
                  </Select>
                </FormControl>
              </SimpleGrid>

              <HStack spacing={4} mt={6} justifyContent="flex-end" w="full">
                <Button
                  leftIcon={<SearchIcon />}
                  colorScheme="blue"
                  onClick={handleSearch}
                  isLoading={logsLoading}
                  size="md"
                  fontWeight="medium"
                >
                  Search
                </Button>
                <Button 
                  variant="outline" 
                  onClick={handleClear}
                  size="md"
                  fontWeight="medium"
                >
                  Clear
                </Button>
                <IconButton
                  aria-label="Refresh"
                  icon={<RepeatIcon />}
                  onClick={() => refetchLogs()}
                  isLoading={logsLoading}
                  size="md"
                  variant="outline"
                />
              </HStack>
            </CardBody>
          </Card>

          {/* Logs Table */}
          <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" w="full">
            <CardBody>
              {logsLoading ? (
                <Flex justify="center" align="center" py={8}>
                  <Spinner size="xl" />
                  <Text ml={4}>Loading logs...</Text>
                </Flex>
              ) : logsError ? (
                <VStack spacing={2} py={8}>
                  <Text textAlign="center" color="red.500" fontWeight="bold">
                    Error Loading Logs
                  </Text>
                  <Text textAlign="center" color="red.400" fontSize="sm">
                    {(() => {
                      const error = logsError as any;
                      if (error?.response?.data?.detail) {
                        const detail = error.response.data.detail;
                        if (typeof detail === 'string') return detail;
                        if (typeof detail === 'object') return detail.message || detail.detail || JSON.stringify(detail);
                        return String(detail);
                      }
                      return error?.message || 'Unknown error';
                    })()}
                  </Text>
                  <Button
                    size="sm"
                    colorScheme="blue"
                    onClick={() => refetchLogs()}
                  >
                    Retry
                  </Button>
                </VStack>
              ) : logsData && logsData.logs && Array.isArray(logsData.logs) && logsData.logs.length > 0 ? (
                <>
                  <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" w="full">
                    <CardBody p={0}>
                      <TableContainer w="full" overflowX="auto">
                        <Table variant="simple" size="md" w="full">
                          <Thead bg={theadBg}>
                            <Tr>
                              <Th fontWeight="semibold" color="gray.700" py={3}>Timestamp</Th>
                              <Th fontWeight="semibold" color="gray.700">Level</Th>
                              <Th fontWeight="semibold" color="gray.700">Service</Th>
                              <Th fontWeight="semibold" color="gray.700">Message</Th>
                              <Th fontWeight="semibold" color="gray.700">Jaeger Trace</Th>
                            </Tr>
                          </Thead>
                          <Tbody>
                            {(Array.isArray(logsData.logs) ? logsData.logs : []).map((log: LogEntry, index: number) => {
                              // Normalize timestamp field (OpenSearch uses @timestamp, we use timestamp)
                          const timestamp = log.timestamp || log['@timestamp'] || log.time || '';
                          // Normalize level field
                          const level = log.level || 'INFO';
                          // Normalize service field
                          const service = log.service || 'unknown';
                          // Normalize message field
                          const message = log.message || '';
                          // Extract Jaeger trace URL or trace ID
                          const jaegerTraceUrl = log.jaeger_trace_url || log['jaeger_trace_url'] || '';
                          const traceId = log.trace_id || log['trace_id'] || '';
                          // Build Jaeger URL - use provided URL or construct from trace_id
                          let jaegerUrl = '';
                          if (jaegerTraceUrl) {
                            // If it's already a full URL, use it
                            if (jaegerTraceUrl.startsWith('http')) {
                              jaegerUrl = jaegerTraceUrl;
                            } else {
                              // If it's just a trace ID, construct the URL
                              const jaegerBaseUrl = process.env.NEXT_PUBLIC_JAEGER_URL || 'http://localhost:16686';
                              jaegerUrl = `${jaegerBaseUrl}/trace/${jaegerTraceUrl}`;
                            }
                          } else if (traceId) {
                            // Construct URL from trace_id
                            const jaegerBaseUrl = process.env.NEXT_PUBLIC_JAEGER_URL || 'http://localhost:16686';
                            jaegerUrl = `${jaegerBaseUrl}/trace/${traceId}`;
                          }
                          
                              return (
                                <Tr 
                                  key={index}
                                  _hover={{ bg: rowHoverBg }}
                                  transition="background 0.2s"
                                >
                                  <Td fontSize="sm" color="gray.600" py={3}>
                                    {formatTimestamp(timestamp)}
                                  </Td>
                                  <Td>
                                    <Badge 
                                      colorScheme={getLevelColor(level)}
                                      fontSize="xs"
                                      px={2}
                                      py={1}
                                      borderRadius="md"
                                      fontWeight="semibold"
                                    >
                                      {level}
                                    </Badge>
                                  </Td>
                                  <Td>
                                    <Text fontSize="sm" fontWeight="medium" color="gray.700">
                                      {service}
                                    </Text>
                                  </Td>
                                  <Td>
                                    <Text 
                                      noOfLines={2} 
                                      maxW="500px"
                                      fontSize="sm"
                                      color="gray.700"
                                      fontFamily="mono"
                                    >
                                      {message}
                                    </Text>
                                  </Td>
                                  <Td>
                                    {traceId ? (
                                      <Button
                                        size="sm"
                                        colorScheme="blue"
                                        variant="link"
                                        onClick={() => router.push(`/traces?traceId=${traceId}`)}
                                        fontSize="sm"
                                        fontWeight="medium"
                                        _hover={{ textDecoration: "underline" }}
                                      >
                                        View Trace
                                      </Button>
                                    ) : (
                                      <Text color="gray.400" fontSize="sm">-</Text>
                                    )}
                                  </Td>
                                </Tr>
                              );
                            })}
                          </Tbody>
                        </Table>
                      </TableContainer>
                    </CardBody>
                  </Card>

                  {/* Pagination */}
                  {logsData.total_pages > 1 && (
                    <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" mt={4} w="full">
                      <CardBody py={3}>
                        <Flex justify="space-between" align="center" w="full">
                          <Text fontSize="sm" color="gray.600" fontWeight="medium">
                            Page {logsData.page} of {logsData.total_pages} ({logsData.total?.toLocaleString() || 0} total logs)
                          </Text>
                          <HStack spacing={2}>
                            <IconButton
                              aria-label="Previous page"
                              icon={<ChevronLeftIcon />}
                              onClick={() => setPage((p) => Math.max(1, p - 1))}
                              isDisabled={page === 1}
                              size="sm"
                              variant="outline"
                            />
                            <Text fontSize="sm" fontWeight="bold" color="gray.700" minW="30px" textAlign="center">
                              {page}
                            </Text>
                            <IconButton
                              aria-label="Next page"
                              icon={<ChevronRightIcon />}
                              onClick={() =>
                                setPage((p) => Math.min(logsData.total_pages, p + 1))
                              }
                              isDisabled={page === logsData.total_pages}
                              size="sm"
                              variant="outline"
                            />
                          </HStack>
                        </Flex>
                      </CardBody>
                    </Card>
                  )}
                </>
              ) : logsData && logsData.total === 0 ? (
                <VStack spacing={2} py={8}>
                  <Text textAlign="center" color="gray.500" fontWeight="medium">
                    No logs found for the selected filters.
                  </Text>
                  <Text fontSize="sm" color="gray.400">
                    Total: {logsData.total || 0} logs. Try adjusting the time range or removing filters.
                  </Text>
                  <HStack spacing={2} justify="center" mt={2}>
                    <Button size="xs" variant="outline" onClick={handleClear}>
                      Clear Filters
                    </Button>
                    <Button size="xs" variant="outline" onClick={() => refetchLogs()}>
                      Refresh
                    </Button>
                  </HStack>
                </VStack>
              ) : (
                <VStack spacing={2} py={8}>
                  <Text textAlign="center" color="gray.500">
                    {logsData ? 'No logs data available.' : 'Waiting for data...'}
                  </Text>
                  {isAuthenticated && (
                    <>
                      <Text fontSize="sm" color="gray.400" textAlign="center">
                        Make sure OpenSearch has logs indexed and your time range includes log entries.
                      </Text>
                      <Button size="sm" variant="outline" onClick={() => refetchLogs()}>
                        Refresh
                      </Button>
                    </>
                  )}
                </VStack>
              )}
            </CardBody>
          </Card>
        </VStack>
      </ContentLayout>
    </>
  );
};

export default LogsPage;

