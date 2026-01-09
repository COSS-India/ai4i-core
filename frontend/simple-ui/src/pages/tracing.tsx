// Custom Tracing UI - Step-by-step visualization like orchestrator demo

import React, { useState } from 'react';
import Head from 'next/head';
import { useRouter } from 'next/router';
import {
  Box,
  Button,
  VStack,
  HStack,
  Text,
  useColorModeValue,
  Input,
  Alert,
  AlertIcon,
  Code,
  Select,
  Spinner,
  Link,
} from '@chakra-ui/react';
import { useQuery } from '@tanstack/react-query';
import ContentLayout from '../components/common/ContentLayout';
import { jaegerService } from '../services/jaegerService';

const TracingPage: React.FC = () => {
  const router = useRouter();
  const [traceIdInput, setTraceIdInput] = useState<string>('');
  const [selectedService, setSelectedService] = useState<string>('');

  const bgColor = useColorModeValue('white', 'gray.800');
  const borderColor = useColorModeValue('gray.200', 'gray.700');

  // Fetch services
  const { data: services = [] } = useQuery({
    queryKey: ['jaeger-services'],
    queryFn: () => jaegerService.getServices(),
  });

  // Fetch recent traces
  const { data: traces = [], isLoading: tracesLoading } = useQuery({
    queryKey: ['jaeger-traces', selectedService],
    queryFn: () =>
      jaegerService.searchTraces({
        service: selectedService || undefined,
        limit: 10,
        lookback: '1h',
      }),
    enabled: !!selectedService,
  });

  const handleViewTrace = () => {
    if (traceIdInput.trim()) {
      router.push(`/tracing/${traceIdInput.trim()}`);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleViewTrace();
    }
  };

  const handleSelectTrace = (traceId: string) => {
    setTraceIdInput(traceId);
    router.push(`/tracing/${traceId}`);
  };


  return (
    <>
      <Head>
        <title>Request Tracing - AI4Inclusion</title>
      </Head>

      <ContentLayout>
        <VStack spacing={6} align="stretch" maxW="800px" mx="auto">
          {/* Header */}
          <Box textAlign="center">
            <Text fontSize="2xl" fontWeight="bold" color="gray.800" mb={2}>
              🎯 Request Tracing Visualization
            </Text>
            <Text fontSize="sm" color="gray.600">
              Enter a trace ID to view step-by-step visualization
            </Text>
          </Box>

          {/* Trace ID Input */}
          <Box
            bg={bgColor}
            borderRadius="lg"
            p={6}
            border="1px solid"
            borderColor={borderColor}
            boxShadow="md"
          >
            <VStack spacing={4}>
              <Text fontSize="sm" fontWeight="600" color="gray.700">
                Trace ID
              </Text>
              <HStack w="full" spacing={3}>
                <Input
                  placeholder="e.g., 824fe5e6e3efec99a6fead8c2865d27e"
                  value={traceIdInput}
                  onChange={(e) => setTraceIdInput(e.target.value)}
                  onKeyPress={handleKeyPress}
                  size="lg"
                  fontFamily="mono"
                  fontSize="sm"
                />
                <Button
                  colorScheme="blue"
                  onClick={handleViewTrace}
                  isDisabled={!traceIdInput.trim()}
                  size="lg"
                  px={8}
                >
                  View Trace
                </Button>
              </HStack>

              {/* Service and Recent Traces */}
              <VStack w="full" spacing={3} align="stretch">
                <Box>
                  <Text fontSize="xs" fontWeight="600" color="gray.700" mb={2}>
                    Or select a service to see recent traces:
                  </Text>
                  <Select
                    placeholder="Select Service"
                    value={selectedService}
                    onChange={(e) => setSelectedService(e.target.value)}
                    size="md"
                  >
                    {services.map((service) => (
                      <option key={service} value={service}>
                        {service}
                      </option>
                    ))}
                  </Select>
                </Box>

                {selectedService && (
                  <Box>
                    {tracesLoading ? (
                      <HStack justify="center" py={4}>
                        <Spinner size="sm" />
                        <Text fontSize="xs" color="gray.600">Loading traces...</Text>
                      </HStack>
                    ) : traces.length > 0 ? (
                      <VStack align="stretch" spacing={2}>
                        <Text fontSize="xs" fontWeight="600" color="gray.700">
                          Recent Traces ({traces.length}):
                        </Text>
                        <VStack align="stretch" spacing={1} maxH="200px" overflowY="auto">
                          {traces.map((trace) => (
                            <Button
                              key={trace.traceID}
                              size="sm"
                              variant="outline"
                              justifyContent="flex-start"
                              fontFamily="mono"
                              fontSize="xs"
                              onClick={() => handleSelectTrace(trace.traceID)}
                              _hover={{ bg: 'blue.50', borderColor: 'blue.300' }}
                            >
                              {trace.traceID.substring(0, 16)}... ({trace.spans.length} spans)
                            </Button>
                          ))}
                        </VStack>
                      </VStack>
                    ) : (
                      <Alert status="warning" fontSize="xs">
                        <AlertIcon />
                        <Text fontSize="xs">No traces found for {selectedService} in the last hour.</Text>
                      </Alert>
                    )}
                  </Box>
                )}
              </VStack>

              <Alert status="info" fontSize="xs">
                <AlertIcon />
                <VStack align="start" spacing={1}>
                  <Text fontSize="xs">
                    Enter a trace ID from Jaeger to view the complete visualization.
                  </Text>
                  <Text fontSize="xs" color="gray.600">
                    💡 <strong>Tip:</strong> Since Jaeger uses in-memory storage, traces are lost on restart. 
                    Make a request to any service first to generate new traces.
                  </Text>
                  {process.env.NEXT_PUBLIC_JAEGER_URL && (
                    <HStack spacing={2} mt={2}>
                      <Link href={process.env.NEXT_PUBLIC_JAEGER_URL} isExternal fontSize="xs" color="blue.500">
                        Open Jaeger UI →
                      </Link>
                    </HStack>
                  )}
                </VStack>
              </Alert>
            </VStack>
          </Box>
        </VStack>
      </ContentLayout>
    </>
  );
};

export default TracingPage;

