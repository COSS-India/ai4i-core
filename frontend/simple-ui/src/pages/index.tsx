// Home page (landing page) with service overview and navigation cards

import {
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Heading,
  Icon,
  SimpleGrid,
  Stat,
  StatLabel,
  StatNumber,
  Text,
  VStack,
  useColorModeValue,
} from "@chakra-ui/react";
import Head from "next/head";
import { useRouter } from "next/router";
import React, { useState } from "react";
import { FaMicrophone } from "react-icons/fa";
import {
  IoGitMergeOutline,
  IoLanguageOutline,
  IoSparklesOutline,
  IoVolumeHighOutline,
  IoServerOutline,
} from "react-icons/io5";
import ContentLayout from "../components/common/ContentLayout";
import { useAuth } from "../hooks/useAuth";
import { useFeatureFlag } from "../hooks/useFeatureFlag";

const HomePage: React.FC = () => {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();
  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");
  const hoverBg = useColorModeValue("gray.50", "gray.700");


  const handleServiceClick = async (path: string) => {
    console.log("handleServiceClick called:", {
      path,
      isAuthenticated,
      isLoading,
    });

    if (isLoading) {
      console.log("HomePage: Auth still loading, waiting...");
      return;
    }

    // All services require authentication, so check if user is authenticated
    if (!isAuthenticated) {
      console.log("HomePage: User not authenticated, redirecting to /auth");
      // Store the intended destination in sessionStorage to redirect after login
      if (typeof window !== 'undefined') {
        sessionStorage.setItem('redirectAfterAuth', path);
      }
      router.push("/auth");
      return;
    }

    // User is authenticated - navigate to the service
    console.log("HomePage: User authenticated, navigating to:", path);
    router.push(path);
  };

  // Feature flags for each service
  const asrEnabled = useFeatureFlag({ flagName: "asr-enabled" });
  const ttsEnabled = useFeatureFlag({ flagName: "tts-enabled" });
  const nmtEnabled = useFeatureFlag({ flagName: "nmt-enabled" });
  const llmEnabled = useFeatureFlag({ flagName: "llm-enabled" });
  const pipelineEnabled = useFeatureFlag({ flagName: "pipeline-enabled" });
  const modelManagementEnabled = useFeatureFlag({ flagName: "model-management-enabled" });

  const services = [
    {
      id: "asr",
      title: "ASR – Automatic Speech Recognition",
      description: "Convert speech to text in 12+ Indic languages",
      icon: FaMicrophone,
      path: "/asr",
      color: "orange",
      enabled: asrEnabled.isEnabled,
    },
    {
      id: "tts",
      title: "TTS – Text-to-Speech",
      description:
        "Convert text to natural, human-like speech in multiple Indic languages and voices",
      icon: IoVolumeHighOutline,
      path: "/tts",
      color: "blue",
      enabled: ttsEnabled.isEnabled,
    },
    {
      id: "nmt",
      title: "Text Translation",
      description: "Translate text between 22+ Indic languages",
      icon: IoLanguageOutline,
      path: "/nmt",
      color: "green",
      enabled: nmtEnabled.isEnabled,
    },
    {
      id: "llm",
      title: "LLM",
      description: "Enable contextual translation",
      icon: IoSparklesOutline,
      path: "/llm",
      color: "pink",
      enabled: llmEnabled.isEnabled,
    },
    {
      id: "pipeline",
      title: "Pipeline",
      description:
        "Chain multiple Language AI services together for seamless end-to-end workflows",
      icon: IoGitMergeOutline,
      path: "/pipeline",
      color: "purple",
      enabled: pipelineEnabled.isEnabled,
    },
    {
      id: "model-management",
      title: "Model Management",
      description:
        "Manage and configure AI models.",
      icon: IoServerOutline,
      path: "/model-management",
      color: "cyan",
      enabled: modelManagementEnabled.isEnabled,
    },
  ].filter((service) => service.enabled); // Filter out disabled services

  return (
    <>
      <Head>
        <title>AI4Inclusion Console</title>
        <meta
          name="description"
          content="Test ASR, TTS, NMT, LLM (GPT OSS 20B), and Pipeline microservices with a modern web interface"
        />
      </Head>

      <ContentLayout>
        <VStack 
          spacing={10} 
          w="full" 
          h="full" 
          justify="center"
          align="center"
        >
          {/* Hero Section */}
          <Box textAlign="center" w="full">
            <Heading size="lg" fontWeight="bold" color="gray.800" mb={2}>
              AI Accessibility Studio
            </Heading>
            <Text fontSize="sm" color="gray.600" maxW="600px" mx="auto">
              Test and explore NLP and LLM models
            </Text>
          </Box>

          {/* Service Cards Grid */}
          <SimpleGrid
            columns={{ base: 1, sm: 2, md: 2, lg: 3, xl: 3 }}
            spacing={6}
            w="full"
            maxW="1200px"
            mx="auto"
            justifyItems="center"
          >
            {services.map((service) => (
              <Card
                key={service.id}
                bg={cardBg}
                border="1px"
                borderColor={cardBorder}
                borderRadius="xl"
                boxShadow="lg"
                overflow="hidden"
                _hover={{
                  transform: "translateY(-6px)",
                  boxShadow: "2xl",
                  borderColor: `${service.color}.300`,
                }}
                transition="all 0.3s ease"
                w={{ base: "100%", sm: "320px", md: "320px", lg: "320px", xl: "320px" }}
                h="260px"
                position="relative"
                display="flex"
                flexDirection="column"
              >
                {/* Colored top border accent */}
                <Box
                  position="absolute"
                  top={0}
                  left={0}
                  right={0}
                  h="4px"
                  bgGradient={`linear(to-r, ${service.color}.400, ${service.color}.600)`}
                />
                
                <CardHeader textAlign="center" pb={3} pt={4} flexShrink={0}>
                  <VStack spacing={3} align="center">
                    <Box
                      p={3}
                      borderRadius="full"
                      bg={`${service.color}.50`}
                      _dark={{ bg: `${service.color}.900` }}
                      display="flex"
                      alignItems="center"
                      justifyContent="center"
                    >
                      <Icon
                        as={service.icon}
                        boxSize={7}
                        color={`${service.color}.600`}
                      />
                    </Box>
                    <Heading size="sm" color="gray.800" fontWeight="semibold" textAlign="center">
                      {service.title}
                    </Heading>
                  </VStack>
                </CardHeader>
                <CardBody pt={0} pb={4} px={4} flex={1} display="flex" flexDirection="column" justifyContent="space-between">
                  <VStack spacing={3} h="full" justify="space-between" align="center">
                    <Text
                      color="gray.600"
                      textAlign="center"
                      lineHeight="1.5"
                      fontSize="sm"
                      noOfLines={3}
                      flex={1}
                      display="flex"
                      alignItems="center"
                      justifyContent="center"
                    >
                      {service.description}
                    </Text>

                    {/* Auth-aware navigation button */}
                    <Button
                      colorScheme={service.color}
                      size="md"
                      w="full"
                      fontWeight="semibold"
                      onClick={(e) => {
                        e.preventDefault();
                        handleServiceClick(service.path);
                      }}
                      _hover={{
                        transform: "translateY(-2px)",
                        boxShadow: "md",
                      }}
                      transition="all 0.2s"
                      flexShrink={0}
                    >
                      Try it now
                    </Button>
                  </VStack>
                </CardBody>
              </Card>
            ))}
          </SimpleGrid>

          {/* Quick Stats Section */}
          <Box w="full" maxW="800px" mx="auto">
            <Heading size="lg" textAlign="center" mb={8} color="gray.800">
              Platform Insights
            </Heading>
            <SimpleGrid
              columns={{ base: 1, md: 2 }}
              spacing={8}
              justifyItems="center"
            >
              <Stat textAlign="center">
                <StatLabel color="gray.600" fontSize="sm">
                  Total Services
                </StatLabel>
                <StatNumber color="orange.600" fontSize="2xl">
                  {services.length}
                </StatNumber>
              </Stat>
              <Stat textAlign="center">
                <StatLabel color="gray.600" fontSize="sm">
                  Supported Languages
                </StatLabel>
                <StatNumber color="orange.600" fontSize="2xl">
                  22+
                </StatNumber>
              </Stat>
            </SimpleGrid>
          </Box>

          {/* Getting Started section removed per requirements */}
        </VStack>
      </ContentLayout>
    </>
  );
};

export default HomePage;
