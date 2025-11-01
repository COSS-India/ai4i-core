// Home page (landing page) with service overview and navigation cards

import React, { useState } from 'react';
import Head from 'next/head';
import { useRouter } from 'next/router';
import {
  Box,
  Heading,
  Text,
  SimpleGrid,
  Card,
  CardBody,
  CardHeader,
  Button,
  VStack,
  useColorModeValue,
  Icon,
  Stat,
  StatLabel,
  StatNumber,
  StatHelpText,
} from '@chakra-ui/react';
import {
  IoVolumeHighOutline,
  IoLanguageOutline,
  IoGitMergeOutline,
  IoSparklesOutline,
} from 'react-icons/io5';
import { FaMicrophone } from 'react-icons/fa';
import ContentLayout from '../components/common/ContentLayout';
import { useAuth } from '../hooks/useAuth';
import AuthModal from '../components/auth/AuthModal';

const HomePage: React.FC = () => {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [pendingNavigation, setPendingNavigation] = useState<string | null>(null);
  const cardBg = useColorModeValue('white', 'gray.800');
  const cardBorder = useColorModeValue('gray.200', 'gray.700');
  const hoverBg = useColorModeValue('gray.50', 'gray.700');

  // Navigate when authenticated and there's a pending navigation
  React.useEffect(() => {
    console.log('HomePage useEffect:', { isAuthenticated, isLoading, pendingNavigation, showAuthModal });
    if (!isLoading && isAuthenticated && pendingNavigation) {
      console.log('✅ Authentication detected, navigating to pending route:', pendingNavigation);
      const navPath = pendingNavigation;
      setPendingNavigation(null); // Clear before navigation
      setShowAuthModal(false); // Close modal
      router.push(navPath);
    }
  }, [isAuthenticated, isLoading, pendingNavigation, router, showAuthModal]);

  // Handle case where user becomes authenticated but there's no pending navigation
  React.useEffect(() => {
    if (!isLoading && isAuthenticated && showAuthModal) {
      console.log('HomePage: User authenticated, closing modal');
      setShowAuthModal(false);
      if (!pendingNavigation && router.pathname !== '/') {
        console.log('HomePage: Redirecting to home after login');
        router.push('/');
      }
    }
  }, [isAuthenticated, isLoading, showAuthModal, pendingNavigation, router]);

  const handleServiceClick = async (path: string) => {
    console.log('handleServiceClick called:', { path, isAuthenticated, isLoading });

    if (isLoading) {
      console.log('HomePage: Auth still loading, waiting...');
      return;
    }

    if (isAuthenticated) {
      console.log('HomePage: User authenticated, navigating to:', path);
      setPendingNavigation(null);
      setShowAuthModal(false);
      await new Promise((resolve) => setTimeout(resolve, 50));
      router.push(path);
    } else {
      console.log('HomePage: User not authenticated, showing modal for:', path);
      setPendingNavigation(path);
      setShowAuthModal(true);
    }
  };

  const handleAuthModalClose = () => {
    setShowAuthModal(false);
  };

  const services = [
    {
      id: 'asr',
      title: 'ASR – Automatic Speech Recognition',
      description: 'Convert speech to text in 22+ Indian languages',
      icon: FaMicrophone,
      path: '/asr',
      color: 'orange',
    },
    {
      id: 'tts',
      title: 'TTS – Text-to-Speech',
      description:
        'Convert text to natural, human-like speech in multiple Indian languages and voices',
      icon: IoVolumeHighOutline,
      path: '/tts',
      color: 'blue',
    },
    {
      id: 'nmt',
      title: 'Text Translation',
      description: 'Translate text between 22+ Indian languages',
      icon: IoLanguageOutline,
      path: '/nmt',
      color: 'green',
    },
    {
      id: 'llm',
      title: 'LLM – GPT OSS 20B',
      description:
        'Translate and process text using GPT OSS 20B large language model with advanced capabilities',
      icon: IoSparklesOutline,
      path: '/llm',
      color: 'pink',
    },
    {
      id: 'pipeline',
      title: 'Pipeline',
      description:
        'Chain multiple Language AI services together for seamless end-to-end workflows',
      icon: IoGitMergeOutline,
      path: '/pipeline',
      color: 'purple',
    },
  ];

  const stats = [
    { label: 'Total Services', value: '5' },
    { label: 'Supported Languages', value: '22+' },
    { label: 'Uptime', value: '99.9%' },
  ];

  return (
    <>
      <Head>
        <title>Simple UI - AI Accessibility Studio</title>
        <meta
          name="description"
          content="Test ASR, TTS, NMT, LLM (GPT OSS 20B), and Pipeline microservices with a modern web interface"
        />
      </Head>

      <ContentLayout>
        <VStack spacing={12} w="full">
          {/* Hero Section */}
          <Box textAlign="center" pt="2rem" pb="4rem">
            <Heading size="xl" fontWeight="bold" color="gray.800" mb={4}>
              AI Accessibility Studio
            </Heading>
            <Text fontSize="lg" color="gray.600" maxW="600px" mx="auto">
              Test and explore Speech, Text, and Translation models in real time.
            </Text>
          </Box>

          {/* Service Cards Grid */}
          <SimpleGrid
            columns={{ base: 1, md: 2, lg: 2, xl: 5 }}
            spacing={6}
            w="full"
            maxW="1600px"
            mx="auto"
          >
            {services.map((service) => (
              <Card
                key={service.id}
                bg={cardBg}
                border="1px"
                borderColor={cardBorder}
                borderRadius="lg"
                boxShadow="md"
                _hover={{
                  transform: 'translateY(-4px)',
                  boxShadow: 'xl',
                  bg: hoverBg,
                }}
                transition="all 0.2s"
                h="full"
              >
                <CardHeader textAlign="center" pb={4}>
                  <VStack spacing={3}>
                    <Icon
                      as={service.icon}
                      boxSize={10}
                      color={`${service.color}.500`}
                    />
                    <Heading size="md" color="gray.800">
                      {service.title}
                    </Heading>
                  </VStack>
                </CardHeader>
                <CardBody pt={0}>
                  <VStack spacing={4} h="full">
                    <Text
                      color="gray.600"
                      textAlign="center"
                      lineHeight="1.5"
                      flex={1}
                      fontSize="sm"
                    >
                      {service.description}
                    </Text>

                    {/* Auth-aware navigation button */}
                    <Button
                      colorScheme={service.color}
                      size="md"
                      w="full"
                      onClick={(e) => {
                        e.preventDefault();
                        handleServiceClick(service.path);
                      }}
                      _hover={{
                        transform: 'translateY(-1px)',
                      }}
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
            <SimpleGrid columns={{ base: 1, md: 3 }} spacing={8}>
              {stats.map((stat, index) => (
                <Stat key={index} textAlign="center">
                  <StatLabel color="gray.600" fontSize="sm">
                    {stat.label}
                  </StatLabel>
                  <StatNumber color="orange.600" fontSize="2xl">
                    {stat.value}
                  </StatNumber>
                  <StatHelpText color="gray.500">
                    {index === 0 && 'Available Services'}
                    {index === 1 && 'Indian Languages'}
                    {index === 2 && 'Reliability'}
                  </StatHelpText>
                </Stat>
              ))}
            </SimpleGrid>
          </Box>

          {/* Getting Started Section */}
          <Box
            bg="orange.50"
            p={8}
            borderRadius="lg"
            w="full"
            maxW="800px"
            mx="auto"
            textAlign="center"
          >
            <Heading size="md" color="gray.800" mb={4}>
              Getting Started
            </Heading>
            <Text color="gray.600" mb={6}>
              Set up your API key to start testing the AI services. Each service supports
              real-time processing and provides detailed statistics.
            </Text>
            <Button
              colorScheme="orange"
              size="lg"
              onClick={() => {
                window.dispatchEvent(new CustomEvent('open-api-key-modal'));
              }}
            >
              Set Up API Key
            </Button>
          </Box>
        </VStack>
      </ContentLayout>

      {/* Auth Modal for service access */}
      <AuthModal
        isOpen={showAuthModal}
        onClose={handleAuthModalClose}
        initialMode="login"
      />
    </>
  );
};

export default HomePage;
