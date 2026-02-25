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
import React, { useState, useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeftIcon, ChevronRightIcon, SearchIcon, RepeatIcon } from "@chakra-ui/icons";
import ContentLayout from "../components/common/ContentLayout";
import { useAuth } from "../hooks/useAuth";
import { useRouter } from "next/router";
import { getJwtToken } from "../services/api";
import { getTenantIdFromToken } from "../utils/helpers";
import {
  searchLogs,
  getLogAggregations,
  getServicesWithLogs,
  LogEntry,
  LogSearchResponse,
  LogAggregationResponse,
} from "../services/observabilityService";
import { useToastWithDeduplication } from "../hooks/useToastWithDeduplication";
import { listTenants } from "../services/multiTenantService";

/**
 * Convert datetime-local format (YYYY-MM-DDTHH:mm) to ISO format (YYYY-MM-DDTHH:mm:ss.sssZ)
 * This ensures the timestamp is properly formatted for OpenSearch queries
 */
const convertToISOFormat = (datetimeLocal: string): string => {
  if (!datetimeLocal || datetimeLocal.trim() === "") {
    return "";
  }
  
  // Parse the datetime-local string (YYYY-MM-DDTHH:mm)
  // Treat it as local time and convert to ISO format
  try {
    // If the string doesn't have seconds, add :00
    let normalized = datetimeLocal;
    if (!normalized.includes(":")) {
      return ""; // Invalid format
    }
    
    // Count colons to determine format
    const colonCount = (normalized.match(/:/g) || []).length;
    if (colonCount === 1) {
      // Format: YYYY-MM-DDTHH:mm - add seconds
      normalized = normalized + ":00";
    }
    
    // Parse as local time and convert to ISO (UTC)
    const date = new Date(normalized);
    if (isNaN(date.getTime())) {
      console.warn(`Invalid datetime format: ${datetimeLocal}`);
      return "";
    }
    
    // Return ISO format string
    return date.toISOString();
  } catch (error) {
    console.error(`Error converting datetime to ISO: ${datetimeLocal}`, error);
    return "";
  }
};

const LogsPage: React.FC = () => {
  const toast = useToastWithDeduplication();
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading, user } = useAuth();
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(10);
  const [clientPage, setClientPage] = useState(1); // Client-side pagination for filtered logs
  
  // Filter input values (what user types/selects - not applied until Search is clicked)
  const [service, setService] = useState<string>("");
  const [level, setLevel] = useState<string>("");
  const [searchText, setSearchText] = useState<string>("");
  const [startTime, setStartTime] = useState<string>("");
  const [endTime, setEndTime] = useState<string>("");
  const [selectedTenantId, setSelectedTenantId] = useState<string>(""); // Admin-only tenant filter
  
  // Applied filter values (what's actually used in the query)
  const [appliedService, setAppliedService] = useState<string>("");
  const [appliedLevel, setAppliedLevel] = useState<string>("");
  const [appliedSearchText, setAppliedSearchText] = useState<string>("");
  const [appliedStartTime, setAppliedStartTime] = useState<string>("");
  const [appliedEndTime, setAppliedEndTime] = useState<string>("");
  const [appliedTenantId, setAppliedTenantId] = useState<string>("");
  
  // Check if user is admin
  const isAdmin = user?.roles?.includes('ADMIN') || false;
  
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

  // Redirect if user doesn't have tenant_id (but allow admins)
  useEffect(() => {
    if (!authLoading && isAuthenticated) {
      const tenantId = getTenantIdFromToken();
      const isAdmin = user?.roles?.includes('ADMIN') || false;
      if (!tenantId && !isAdmin) {
        toast({
          title: "Access Denied",
          description: "You need to be assigned to a tenant to view logs.",
          status: "error",
          duration: 5000,
          isClosable: true,
        });
        router.push("/");
      }
    }
  }, [isAuthenticated, authLoading, user, router, toast]);

  // Fetch services list (only if authenticated)
  const { data: services, isLoading: servicesLoading, error: servicesError } = useQuery({
    queryKey: ["logs-services"],
    queryFn: getServicesWithLogs,
    enabled: isAuthenticated,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  // Fetch tenants list (only for admins)
  const { data: tenantsData, isLoading: tenantsLoading, error: tenantsError } = useQuery({
    queryKey: ["tenants-list"],
    queryFn: async () => {
      try {
        console.log('Fetching tenants list...');
        const result = await listTenants();
        console.log('Tenants list fetched successfully:', {
          count: result?.count,
          tenantsCount: result?.tenants?.length || 0,
          tenants: result?.tenants,
        });
        return result;
      } catch (error: any) {
        console.error('Error in listTenants queryFn:', error);
        console.error('Error details:', {
          message: error?.message,
          response: error?.response?.data,
          status: error?.response?.status,
          statusText: error?.response?.statusText,
          url: error?.config?.url,
        });
        throw error; // Re-throw to let React Query handle it
      }
    },
    enabled: isAuthenticated && isAdmin,
    staleTime: 5 * 60 * 1000, // 5 minutes
    retry: 1, // Retry once on failure
  });

  // Filter tenants to only show ACTIVE tenants
  const activeTenants = useMemo(() => {
    if (!tenantsData?.tenants || !Array.isArray(tenantsData.tenants)) {
      console.log('No tenants data available:', { tenantsData });
      return [];
    }
    
    // Filter for ACTIVE tenants (case-insensitive, trim whitespace)
    const active = tenantsData.tenants.filter((tenant: any) => {
      const status = String(tenant?.status || '').trim().toUpperCase();
      return status === 'ACTIVE';
    });
    
    console.log('Active tenants filter result:', {
      totalTenants: tenantsData.tenants.length,
      activeCount: active.length,
      allStatuses: tenantsData.tenants.map((t: any) => ({ 
        tenant_id: t.tenant_id, 
        status: t.status,
        statusType: typeof t.status 
      })),
      activeTenants: active.map((t: any) => ({ 
        tenant_id: t.tenant_id, 
        organization_name: t.organization_name 
      }))
    });
    
    return active;
  }, [tenantsData]);

  // Debug: Log admin status, tenant data, and errors
  useEffect(() => {
    if (isAuthenticated && isAdmin) {
      console.log('Logs page - Admin status:', {
        isAdmin,
        userRoles: user?.roles,
        tenantsData: tenantsData,
        tenantsCount: tenantsData?.tenants?.length || 0,
        activeTenantsCount: activeTenants.length,
        tenantsError: tenantsError,
      });
    }
    if (tenantsError) {
      console.error('Error fetching tenants:', tenantsError);
    }
  }, [isAuthenticated, isAdmin, user, tenantsData, activeTenants, tenantsError]);

  // Filter services to only show application services (exclude infrastructure services)
  const filteredServices = useMemo(() => {
    if (!services || !Array.isArray(services)) {
      return [];
    }

    // Define allowed application services
    const allowedServices = [
      'ocr-service',
      'ner-service',
      'tts-service',
      'nmt-service',
      'pipeline-service',
      'audio-lang',
      'audio-lang-detection-service', // Support both naming conventions
      'asr-service',
      'speaker-diarization-service',
      'transliteration-service',
      'llm-service',
      'language-detection-service',
      'language-detection',
      'language-diarization-service',
      'language-diarization',
      'auth-service',
      'telemetry-service',
    ];

    // Also define patterns for infrastructure services to exclude
    const infrastructurePatterns = [
      /^apisix/i,
      /^fluent-bit/i,
      /^prometheus/i,
      /^grafana/i,
      /^jaeger/i,
      /^opensearch/i,
      /^postgres/i,
      /^redis/i,
      /^influxdb/i,
      /^alertmanager/i,
      /^node-exporter/i,
      /^kube-state/i,
      /^cm-acme/i,
      /^opensearch-cleanup/i,
      /^simple-ui/i,
    ];

    // Filter services: only include services in the allowed list
    return services.filter((service: string) => {
      // Only include services that are explicitly in the allowed list
      return allowedServices.includes(service);
    }).sort(); // Sort alphabetically for better UX
  }, [services]);

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

  // Fetch aggregations (only if authenticated and ADMIN)
  const { data: aggregations, isLoading: aggregationsLoading, error: aggregationsError } = useQuery({
    queryKey: ["logs-aggregations", appliedStartTime, appliedEndTime],
    queryFn: () => {
      // Convert datetime-local format to ISO format for API
      const apiStartTime = appliedStartTime && appliedStartTime.trim() !== "" ? convertToISOFormat(appliedStartTime) : undefined;
      const apiEndTime = appliedEndTime && appliedEndTime.trim() !== "" ? convertToISOFormat(appliedEndTime) : undefined;
      return getLogAggregations({
        start_time: apiStartTime,
        end_time: apiEndTime,
      });
    },
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
      appliedService,
      appliedLevel,
      appliedSearchText,
      appliedStartTime,
      appliedEndTime,
      size, // Include size in query key since we use it for fetch size
      appliedTenantId, // Include tenant_id for admin filtering
    ],
    queryFn: async () => {
      // API has a maximum limit of 100 for size parameter
      // Fetch multiple pages to get all available logs, then filter and paginate client-side
      const fetchSize = 100; // API maximum limit
      
      // Prepare API parameters (using applied values)
      const apiService = appliedService && appliedService.trim() !== "" ? appliedService : undefined;
      const apiLevel = appliedLevel && appliedLevel.trim() !== "" ? appliedLevel : undefined;
      
      console.log('Fetching logs with filters:', {
        service: apiService || 'All Services',
        level: apiLevel || 'All Levels',
        fetchSize,
        startTime: appliedStartTime || 'not set',
        endTime: appliedEndTime || 'not set',
      });
      
      // Convert datetime-local format to ISO format for API
      const apiStartTime = appliedStartTime && appliedStartTime.trim() !== "" ? convertToISOFormat(appliedStartTime) : undefined;
      const apiEndTime = appliedEndTime && appliedEndTime.trim() !== "" ? convertToISOFormat(appliedEndTime) : undefined;
      
      console.log('Time conversion:', {
        startTime_local: appliedStartTime,
        startTime_iso: apiStartTime,
        endTime_local: appliedEndTime,
        endTime_iso: apiEndTime,
      });
      
      // First, fetch page 1 to get total count
      const firstPage = await searchLogs({
        page: 1,
        size: fetchSize,
        service: apiService,
        level: apiLevel,
        search_text: appliedSearchText && appliedSearchText.trim() !== "" ? appliedSearchText : undefined,
        start_time: apiStartTime,
        end_time: apiEndTime,
        tenant_id: isAdmin && appliedTenantId && appliedTenantId.trim() !== "" ? appliedTenantId : undefined,
      });
      
      // Ensure logs is always an array
      if (firstPage && !Array.isArray(firstPage.logs)) {
        console.warn('API returned non-array logs, converting:', firstPage);
        firstPage.logs = [];
      }
      
      const allLogs = firstPage.logs || [];
      const totalPages = firstPage.total_pages || 1;
      
      console.log('First page fetched:', {
        total: firstPage.total,
        logsCount: allLogs.length,
        totalPages,
      });
      
      // Fetch all remaining pages to get all available logs
      if (totalPages > 1) {
        console.log(`Fetching all ${totalPages} pages to get all available logs...`);
        
        // Fetch pages in parallel batches to speed up loading
        const batchSize = 5; // Fetch 5 pages at a time to avoid overwhelming the API
        for (let batchStart = 2; batchStart <= totalPages; batchStart += batchSize) {
          const batchEnd = Math.min(batchStart + batchSize - 1, totalPages);
          const batchPromises = [];
          
          for (let page = batchStart; page <= batchEnd; page++) {
              batchPromises.push(
                searchLogs({
                  page,
                  size: fetchSize,
                  service: apiService,
                  level: apiLevel,
                  search_text: appliedSearchText && appliedSearchText.trim() !== "" ? appliedSearchText : undefined,
                  start_time: apiStartTime,
                  end_time: apiEndTime,
                  tenant_id: isAdmin && appliedTenantId && appliedTenantId.trim() !== "" ? appliedTenantId : undefined,
                }).catch((error) => {
                console.error(`Error fetching page ${page}:`, error);
                return { logs: [] }; // Return empty logs on error
              })
            );
          }
          
          const batchResults = await Promise.all(batchPromises);
          batchResults.forEach((pageResult) => {
            if (pageResult && Array.isArray(pageResult.logs)) {
              allLogs.push(...pageResult.logs);
            }
          });
          
          console.log(`Fetched pages ${batchStart}-${batchEnd}: ${allLogs.length} total logs so far (${Math.round((batchEnd / totalPages) * 100)}% complete)`);
        }
        
        console.log(`Completed fetching: ${allLogs.length} total logs from ${totalPages} pages`);
      }
      
      // Return combined result
      return {
        ...firstPage,
        logs: allLogs,
        total: allLogs.length, // Use actual fetched count
        total_pages: Math.ceil(allLogs.length / fetchSize),
      };
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
        service: service || 'All Services',
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
  }, [logsData, services, appliedService]);

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

  // Set default time range (last 1 hour) - update when page loads or when both are empty
  useEffect(() => {
    // Only set default if both startTime and endTime are empty
    // This ensures we set it once on initial load, but don't override user's manual selections
    if (!startTime && !endTime && !appliedStartTime && !appliedEndTime) {
      const now = new Date();
      const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);
      // Format as YYYY-MM-DDTHH:mm for datetime-local input
      const formatDateTime = (date: Date) => {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        return `${year}-${month}-${day}T${hours}:${minutes}`;
      };
      const formattedNow = formatDateTime(now);
      const formattedOneHourAgo = formatDateTime(oneHourAgo);
      setEndTime(formattedNow);
      setStartTime(formattedOneHourAgo);
      // Also set applied values so initial query runs
      setAppliedEndTime(formattedNow);
      setAppliedStartTime(formattedOneHourAgo);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSearch = () => {
    // Apply all filter values to the query
    setAppliedService(service);
    setAppliedLevel(level);
    setAppliedSearchText(searchText);
    setAppliedStartTime(startTime);
    setAppliedEndTime(endTime);
    setAppliedTenantId(selectedTenantId);
    // Reset pagination
    setPage(1);
    setClientPage(1);
    // Note: React Query will automatically refetch when applied values change
  };

  const handleRefresh = () => {
    // Update time range to include latest logs
    const now = new Date();
    const formatDateTime = (date: Date) => {
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, '0');
      const day = String(date.getDate()).padStart(2, '0');
      const hours = String(date.getHours()).padStart(2, '0');
      const minutes = String(date.getMinutes()).padStart(2, '0');
      return `${year}-${month}-${day}T${hours}:${minutes}`;
    };

    // Use applied time range if available, otherwise use current filter values
    const currentStartTime = appliedStartTime || startTime;
    const currentEndTime = appliedEndTime || endTime;

    // If both startTime and endTime are set, maintain the time range but shift it to now
    if (currentStartTime && currentEndTime) {
      try {
        const startDate = new Date(currentStartTime);
        const endDate = new Date(currentEndTime);
        const timeRangeMs = endDate.getTime() - startDate.getTime();
        
        // Set new endTime to now, and startTime to maintain the same range
        const newEndTime = formatDateTime(now);
        const newStartTime = formatDateTime(new Date(now.getTime() - timeRangeMs));
        
        setEndTime(newEndTime);
        setStartTime(newStartTime);
        // Also update applied values to trigger immediate refresh
        setAppliedEndTime(newEndTime);
        setAppliedStartTime(newStartTime);
      } catch (error) {
        // If parsing fails, just update endTime to now and keep startTime as is
        console.warn('Error parsing time range, updating endTime only:', error);
        const newEndTime = formatDateTime(now);
        setEndTime(newEndTime);
        setAppliedEndTime(newEndTime);
      }
    } else {
      // If time range is not set, set default 1 hour range
      const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);
      const formattedNow = formatDateTime(now);
      const formattedOneHourAgo = formatDateTime(oneHourAgo);
      setEndTime(formattedNow);
      setStartTime(formattedOneHourAgo);
      // Also update applied values
      setAppliedEndTime(formattedNow);
      setAppliedStartTime(formattedOneHourAgo);
    }
    
    // Reset to first page
    // Note: React Query will automatically refetch when applied values change
    setPage(1);
    setClientPage(1);
  };

  const handleClear = () => {
    // Clear filter inputs
    setService("");
    setLevel("");
    setSearchText("");
    setSelectedTenantId(""); // Clear tenant filter
    const now = new Date();
    const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);
    // Format as YYYY-MM-DDTHH:mm for datetime-local input
    const formatDateTime = (date: Date) => {
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, '0');
      const day = String(date.getDate()).padStart(2, '0');
      const hours = String(date.getHours()).padStart(2, '0');
      const minutes = String(date.getMinutes()).padStart(2, '0');
      return `${year}-${month}-${day}T${hours}:${minutes}`;
    };
    const formattedNow = formatDateTime(now);
    const formattedOneHourAgo = formatDateTime(oneHourAgo);
    setEndTime(formattedNow);
    setStartTime(formattedOneHourAgo);
    // Also clear applied values and set default time range
    setAppliedService("");
    setAppliedLevel("");
    setAppliedSearchText("");
    setAppliedTenantId("");
    setAppliedEndTime(formattedNow);
    setAppliedStartTime(formattedOneHourAgo);
    setPage(1);
    setClientPage(1);
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

  // Filter out irrelevant health check, metrics endpoint, infrastructure errors, and Jaeger trace URLs
  const shouldFilterLog = (log: LogEntry): boolean => {
    const message = (log.message || '').toLowerCase();
    
    // Filter patterns for health/metrics endpoints
    const healthMetricsPatterns = [
      // Patterns for /enterprise/metrics and /metrics endpoints
      /\bget\s+\/enterprise\/metrics\b/i,
      /\bget\s+\/metrics\b/i,
      // Patterns for /health endpoints (including /api/v1/*/health)
      /\bget\s+.*\/health\b/i, // Matches /health, /api/v1/llm/health, etc.
      // Patterns for these paths at start of line or after whitespace
      /\/enterprise\/metrics(\s|$|\?|#|\d|-\s*\d)/i,
      /\/metrics(\s|$|\?|#|\d|-\s*\d)/i,
      /\/health(\s|$|\?|#|\d|-\s*\d)/i, // Matches /health anywhere in path
      // Patterns in HTTP log format: "GET /api/v1/llm/health - 200" or "GET /health - 200"
      /\b(get|post|put|delete|patch)\s+.*\/enterprise\/metrics\s+-\s+\d+/i,
      /\b(get|post|put|delete|patch)\s+.*\/metrics\s+-\s+\d+/i,
      /\b(get|post|put|delete|patch)\s+.*\/health\s+-\s+\d+/i, // Matches any path ending in /health
    ];
    
    // Filter patterns for Jaeger trace URLs
    const jaegerPatterns = [
      /\/jaeger\/api\/traces\//i, // Matches /jaeger/api/traces/...
      /jaeger.*trace/i, // Matches any mention of jaeger trace
    ];
    
    // Filter patterns for infrastructure/health check errors
    const infrastructureErrorPatterns = [
      /failed to check server readiness/i,
      /redis health check failed/i,
      /connection closed by server/i,
      /network is unreachable/i,
      /health check failed/i,
      /server readiness/i,
      /connection.*closed/i,
      /network.*unreachable/i,
    ];
    
    // Filter patterns for feature-flags endpoint
    const featureFlagsPatterns = [
      /\/api\/v1\/feature-flags\/evaluate/i,
      /feature-flags\/evaluate/i,
      /\b(get|post|put|delete|patch)\s+.*\/feature-flags\/evaluate/i,
    ];
    
    // Check if message matches any filter pattern
    return healthMetricsPatterns.some(pattern => pattern.test(message)) ||
           jaegerPatterns.some(pattern => pattern.test(message)) ||
           infrastructureErrorPatterns.some(pattern => pattern.test(message)) ||
           featureFlagsPatterns.some(pattern => pattern.test(message));
  };

  // Step 1: First filter out noise (health, metrics, infrastructure errors, feature-flags, etc.)
  // Service/level filters are already applied at API level, so we just need to remove noise
  const allFilteredLogs = useMemo(() => {
    if (!logsData || !logsData.logs || !Array.isArray(logsData.logs)) {
      console.log('No logs data available for filtering');
      return [];
    }
    
    console.log('Filtering logs:', {
      totalFromAPI: logsData.logs.length,
      service: appliedService || 'All Services',
      level: appliedLevel || 'All Levels',
    });
    
    const filtered = logsData.logs.filter((log: LogEntry) => !shouldFilterLog(log));
    
    // Debug logging
    if (logsData.logs.length > 0) {
      const filteredCount = logsData.logs.length - filtered.length;
      console.log(`Filtered logs result:`, {
        originalCount: logsData.logs.length,
        filteredCount: filtered.length,
        noiseRemoved: filteredCount,
        service: appliedService || 'All Services',
        level: appliedLevel || 'All Levels',
      });
      
      if (filtered.length === 0 && logsData.logs.length > 0) {
        console.warn('All logs were filtered out as noise! Sample log messages:', 
          logsData.logs.slice(0, 3).map((log: LogEntry) => log.message?.substring(0, 100))
        );
      }
    }
    
    return filtered;
  }, [logsData, appliedService, appliedLevel]);

  // Calculate filtered statistics for display
  const filteredStats = useMemo(() => {
    const stats = {
      total: allFilteredLogs.length,
      error: 0,
      warn: 0,
      info: 0,
    };
    
    allFilteredLogs.forEach((log: LogEntry) => {
      const logLevel = (log.level || '').toUpperCase();
      if (logLevel === 'ERROR') stats.error++;
      else if (logLevel === 'WARN' || logLevel === 'WARNING') stats.warn++;
      else if (logLevel === 'INFO') stats.info++;
    });
    
    return stats;
  }, [allFilteredLogs]);

  // Calculate pagination for filtered logs
  const totalFilteredLogs = allFilteredLogs.length;
  const totalFilteredPages = Math.ceil(totalFilteredLogs / size);
  
  // Step 2: Get the current page of filtered logs (client-side pagination)
  const filteredLogs = useMemo(() => {
    const startIndex = (clientPage - 1) * size;
    const endIndex = startIndex + size;
    return allFilteredLogs.slice(startIndex, endIndex);
  }, [allFilteredLogs, clientPage, size]);

  // Reset client page when applied filters change
  useEffect(() => {
    setClientPage(1);
  }, [appliedService, appliedLevel, appliedSearchText, appliedStartTime, appliedEndTime, size, appliedTenantId]);

  // Debug: Log filtered results
  useEffect(() => {
    if (logsData && logsData.logs && Array.isArray(logsData.logs) && logsData.logs.length > 0) {
      console.log('Filtered logs:', {
        page: logsData.page,
        totalLogs: logsData.logs.length,
        filteredLogs: filteredLogs.length,
        filteredOut: logsData.logs.length - filteredLogs.length,
        service: appliedService || 'All Services',
      });
    }
  }, [logsData, filteredLogs, appliedService]);

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
                      {filteredStats.total.toLocaleString()}
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
                      {filteredStats.error.toLocaleString()}
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
                      {filteredStats.warn.toLocaleString()}
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
                      {filteredStats.info.toLocaleString()}
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
                {/* Tenant Filter - Admin Only */}
                {isAdmin && (
                  <FormControl>
                    <FormLabel fontWeight="medium">Tenant</FormLabel>
                    <Select
                      value={selectedTenantId || ""}
                      onChange={(e) => {
                        const value = e.target.value;
                        setSelectedTenantId(value === "" ? "" : value);
                        // Don't reset pagination here - wait for Search button
                      }}
                      bg="white"
                      isDisabled={tenantsLoading}
                    >
                      <option value="">All Tenants</option>
                      {tenantsLoading ? (
                        <option value="" disabled>Loading tenants...</option>
                      ) : tenantsError ? (
                        <option value="" disabled>Error loading tenants</option>
                      ) : activeTenants.length > 0 ? (
                        activeTenants.map((tenant: any) => (
                          <option key={tenant.tenant_id} value={tenant.tenant_id}>
                            {tenant.organization_name || tenant.tenant_id}
                          </option>
                        ))
                      ) : (
                        <option value="" disabled>No active tenants found</option>
                      )}
                    </Select>
                  </FormControl>
                )}

                <FormControl>
                  <FormLabel fontWeight="medium">Service</FormLabel>
                    <Select
                      value={service || ""}
                      onChange={(e) => {
                        const value = e.target.value;
                        setService(value === "" ? "" : value);
                        // Don't reset pagination here - wait for Search button
                      }}
                    bg="white"
                  >
                    <option value="">All Services</option>
                    {filteredServices.map((svc) => (
                      <option key={svc} value={svc}>
                        {svc}
                      </option>
                    ))}
                  </Select>
                </FormControl>

                <FormControl>
                  <FormLabel fontWeight="medium">Level</FormLabel>
                    <Select
                      value={level || ""}
                      onChange={(e) => {
                        const value = e.target.value;
                        setLevel(value === "" ? "" : value);
                        // Don't reset pagination here - wait for Search button
                      }}
                    bg="white"
                  >
                    <option value="">All Levels</option>
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
                        setClientPage(1);
                        // Page size change applies immediately (no need for Search button)
                      }}
                    bg="white"
                  >
                    <option value={10}>10</option>
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
                  onClick={handleRefresh}
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
                    onClick={handleRefresh}
                  >
                    Retry
                  </Button>
                </VStack>
              ) : logsData && logsData.logs && Array.isArray(logsData.logs) ? (
                totalFilteredLogs > 0 ? (
                <>
                  {logsData.logs.length > allFilteredLogs.length && (
                    <Alert status="info" borderRadius="md" mb={4}>
                      <AlertIcon />
                      <AlertDescription fontSize="sm">
                        Showing {filteredLogs.length} logs on page {clientPage} of {totalFilteredPages} ({totalFilteredLogs.toLocaleString()} total filtered logs). 
                        Health check, metrics endpoint, feature-flags, infrastructure errors, and Jaeger trace URL logs are hidden.
                      </AlertDescription>
                    </Alert>
                  )}
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
                              <Th fontWeight="semibold" color="gray.700">Trace</Th>
                            </Tr>
                          </Thead>
                          <Tbody>
                            {filteredLogs.map((log: LogEntry, index: number) => {
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

                  {/* Pagination - based on filtered logs */}
                  {totalFilteredPages > 1 && (
                    <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" mt={4} w="full">
                      <CardBody py={3}>
                        <Flex justify="space-between" align="center" w="full">
                          <Text fontSize="sm" color="gray.600" fontWeight="medium">
                            Page {clientPage} of {totalFilteredPages} ({totalFilteredLogs.toLocaleString()} filtered logs)
                          </Text>
                          <HStack spacing={2}>
                            <IconButton
                              aria-label="Previous page"
                              icon={<ChevronLeftIcon />}
                              onClick={() => setClientPage((p) => Math.max(1, p - 1))}
                              isDisabled={clientPage === 1}
                              size="sm"
                              variant="outline"
                            />
                            <Text fontSize="sm" fontWeight="bold" color="gray.700" minW="30px" textAlign="center">
                              {clientPage}
                            </Text>
                            <IconButton
                              aria-label="Next page"
                              icon={<ChevronRightIcon />}
                              onClick={() =>
                                setClientPage((p) => Math.min(totalFilteredPages, p + 1))
                              }
                              isDisabled={clientPage === totalFilteredPages}
                              size="sm"
                              variant="outline"
                            />
                          </HStack>
                        </Flex>
                      </CardBody>
                    </Card>
                  )}
                </>
                ) : logsData.logs.length > 0 ? (
                  <VStack spacing={2} py={8}>
                    <Text textAlign="center" color="gray.500" fontWeight="medium">
                      All logs were filtered out (health checks and metrics endpoints are hidden).
                    </Text>
                    <Text fontSize="sm" color="gray.400">
                      {logsData.logs.length} logs were fetched, but all were filtered. 
                      Try adjusting your filters or time range.
                    </Text>
                    <HStack spacing={2} justify="center" mt={2}>
                      <Button size="xs" variant="outline" onClick={handleClear}>
                        Clear Filters
                      </Button>
                      <Button size="xs" variant="outline" onClick={handleRefresh}>
                        Refresh
                      </Button>
                    </HStack>
                  </VStack>
                ) : (
                  <VStack spacing={2} py={8}>
                    <Text textAlign="center" color="gray.500" fontWeight="medium">
                      No logs found on this page.
                    </Text>
                    <Text fontSize="sm" color="gray.400">
                      Try adjusting your filters or navigating to another page.
                    </Text>
                    <HStack spacing={2} justify="center" mt={2}>
                      <Button size="xs" variant="outline" onClick={handleClear}>
                        Clear Filters
                      </Button>
                      <Button size="xs" variant="outline" onClick={handleRefresh}>
                        Refresh
                      </Button>
                    </HStack>
                  </VStack>
                )
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
                    <Button size="xs" variant="outline" onClick={handleRefresh}>
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
                      <Button size="sm" variant="outline" onClick={handleRefresh}>
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
