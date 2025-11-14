// Home page (landing page) with service overview and navigation cards

import React from 'react';
import Head from 'next/head';
import Link from 'next/link';
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
  Container,
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
} from 'react-icons/io5';
import { FaMicrophone } from 'react-icons/fa';
import ContentLayout from '../components/common/ContentLayout';

const HomePage: React.FC = () => {
  const cardBg = useColorModeValue('white', 'gray.800');
  const cardBorder = useColorModeValue('gray.200', 'gray.700');
  const hoverBg = useColorModeValue('gray.50', 'gray.700');

  const services = [
    {
      id: 'asr',
      title: 'Speech Recognition',
      description: 'Convert speech to text with support for 22+ Indian languages',
      icon: FaMicrophone,
      path: '/asr',
      color: 'orange',
    },
    {
      id: 'tts',
      title: 'Text-to-Speech',
      description: 'Convert text to natural-sounding speech with multiple voice options',
      icon: IoVolumeHighOutline,
      path: '/tts',
      color: 'blue',
    },
    {
      id: 'nmt',
      title: 'Translation',
      description: 'Translate text between 22+ Indian languages with high accuracy',
      icon: IoLanguageOutline,
      path: '/nmt',
      color: 'green',
    },
    {
      id: 'pipeline',
      title: 'Pipeline',
      description: 'Chain multiple services together for end-to-end workflows',
      icon: IoGitMergeOutline,
      path: '/pipeline',
      color: 'purple',
    },
  ];

  const stats = [
    { label: 'Total Services', value: '4' },
    { label: 'Supported Languages', value: '22+' },
    { label: 'Uptime', value: '99.9%' },
  ];

  return (
    <>
      <Head>
        <title>Simple UI - AI Services Testing Interface</title>
        <meta name="description" content="Test ASR, TTS, NMT, and Pipeline microservices with a modern web interface" />
      </Head>

      <ContentLayout>
        <VStack spacing={12} w="full">
          {/* Hero Section */}
          <Box textAlign="center" py="4rem">
            <Heading
              size="xl"
              fontWeight="bold"
              color="gray.800"
              mb={4}
            >
              AI Services Testing Interface
            </Heading>
            <Text
              fontSize="lg"
              color="gray.600"
              maxW="600px"
              mx="auto"
            >
              Test and interact with ASR, TTS, NMT, and Pipeline microservices through a modern, 
              user-friendly web interface. Experience the power of AI4Bharat&apos;s language technologies.
            </Text>
          </Box>

          {/* Service Cards Grid */}
          <SimpleGrid
            columns={{ base: 1, md: 2, lg: 4 }}
            spacing={6}
            w="full"
            maxW="1400px"
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
                    <Link href={service.path} passHref>
                      <Button
                        colorScheme={service.color}
                        size="md"
                        w="full"
                        _hover={{
                          transform: 'translateY(-1px)',
                        }}
                      >
                        Try {service.title}
                      </Button>
                    </Link>
                  </VStack>
                </CardBody>
              </Card>
            ))}
          </SimpleGrid>

          {/* Quick Stats Section */}
          <Box w="full" maxW="800px" mx="auto">
            <Heading size="lg" textAlign="center" mb={8} color="gray.800">
              Platform Statistics
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
              Set up your API key to start testing the AI services. 
              Each service supports real-time processing and provides detailed statistics.
            </Text>
            <Button
              colorScheme="orange"
              size="lg"
              onClick={() => {
                // This will be handled by the Header component's API key modal
                window.dispatchEvent(new CustomEvent('open-api-key-modal'));
              }}
            >
              Set Up API Key
            </Button>
          </Box>
        </VStack>
      </ContentLayout>
    </>
  );
};

export default HomePage;