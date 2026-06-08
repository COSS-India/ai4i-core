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
  Alert,
  AlertIcon,
  AlertDescription,
  Card,
  CardBody,
  useColorModeValue,
} from "@chakra-ui/react";
import Head from "next/head";
import React from "react";
import { SearchIcon } from "@chakra-ui/icons";
import ContentLayout from "../components/common/ContentLayout";
import TraceDetailView from "../components/traces/TraceDetailView";
import { useTraceViewer } from "../hooks/useTraceViewer";

const TracesPage: React.FC = () => {
  const cardBg = useColorModeValue("white", "gray.800");
  const borderColor = useColorModeValue("gray.200", "gray.700");
  const viewer = useTraceViewer();

  return (
    <>
      <Head>
        <title>Trace Viewer - AI4Inclusion Console</title>
        <meta name="description" content="View and analyze request traces" />
      </Head>

      <ContentLayout>
        <VStack spacing={6} w="full" align="stretch" maxW="100%">
          <Box textAlign="center" mb={2}>
            <Heading size="lg" color="gray.800" mb={1}>
              Trace Viewer
            </Heading>
            <Text color="gray.600" fontSize="sm">
              View and analyze request execution traces
            </Text>
          </Box>

          {!viewer.authLoading && !viewer.isAuthenticated && (
            <Alert status="warning">
              <AlertIcon />
              <AlertDescription>
                Please log in to view traces.{" "}
                <Button
                  size="sm"
                  colorScheme="blue"
                  ml={4}
                  onClick={() => viewer.router.push("/auth")}
                >
                  Log In
                </Button>
              </AlertDescription>
            </Alert>
          )}

          <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" w="full">
            <CardBody>
              <FormControl>
                <FormLabel fontWeight="medium" color="gray.700" mb={2}>
                  Search by Trace ID
                </FormLabel>
                <HStack spacing={2}>
                  <Input
                    placeholder="Enter trace ID (e.g., 741229d83d4d22e4de3e9abddaf37e01)..."
                    value={viewer.traceIdSearch}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                      viewer.setTraceIdSearch(e.target.value)
                    }
                    bg="white"
                    fontFamily="mono"
                    fontSize="sm"
                    size="lg"
                    onKeyPress={(e: React.KeyboardEvent<HTMLInputElement>) => {
                      if (e.key === "Enter") viewer.handleSearchByTraceId();
                    }}
                  />
                  <Button
                    colorScheme="blue"
                    onClick={viewer.handleSearchByTraceId}
                    isDisabled={!viewer.traceIdSearch.trim()}
                    leftIcon={<SearchIcon />}
                    size="lg"
                  >
                    Load Trace
                  </Button>
                </HStack>
              </FormControl>
            </CardBody>
          </Card>

          <TraceDetailView
            traceDetailsLoading={viewer.traceDetailsLoading}
            traceError={viewer.traceError}
            traceDetails={viewer.traceDetails}
            processedSpans={viewer.processedSpans}
            traceStatus={viewer.traceStatus}
            primaryErrorMessage={viewer.primaryErrorMessage}
            traceStartTime={viewer.traceStartTime}
            traceDuration={viewer.traceDuration}
            spanRelationships={viewer.spanRelationships}
            expandedTags={viewer.expandedTags}
            setExpandedTags={viewer.setExpandedTags}
          />
        </VStack>
      </ContentLayout>
    </>
  );
};

export default TracesPage;
