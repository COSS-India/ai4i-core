import {
  Alert,
  AlertDescription,
  AlertIcon,
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Heading,
  HStack,
  Icon,
  SimpleGrid,
  Text,
  VStack,
  useColorModeValue,
} from "@chakra-ui/react";
import Head from "next/head";
import { useRouter } from "next/router";
import React, { useMemo } from "react";
import { showToast } from "../utils/toast";
import { FaMicrophone } from "react-icons/fa";
import {
  IoLanguageOutline,
  IoSparklesOutline,
  IoVolumeHighOutline,
  IoDocumentTextOutline,
  IoSwapHorizontalOutline,
  IoGlobeOutline,
  IoPeopleOutline,
  IoRadioOutline,
  IoPricetagOutline,
} from "react-icons/io5";
import ContentLayout from "../components/common/ContentLayout";
import {
  getExploreServiceCardVisuals,
  getServiceAccent,
  getServiceDescription,
  getServiceTitle,
  servicePath,
  type ServiceId,
} from "../config/serviceMetadata";
import { useAuth } from "../hooks/useAuth";
import DoubleMicrophoneIcon from "../components/common/DoubleMicrophoneIcon";
import { useGuestServices } from "../hooks/useGuestServices";
import { useInferenceTypes } from "../hooks/useInferenceTypes";
import { getPlatformName } from "../config/runtimeConfig";

/** Anonymous users may try LLM without signing in. */
const ANONYMOUS_ALLOWED_SERVICE_IDS = new Set<ServiceId>(["llm"]);

const HomePage: React.FC = () => {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();
  const { isGuest, isLoading: guestServicesLoading, allowedServiceIds } = useGuestServices();
  const { enabledServiceIds, isLoading: inferenceTypesLoading } = useInferenceTypes();
  const availableCardBg = useColorModeValue("white", "ink.800");
  const unavailableCardBg = useColorModeValue("ink.50", "ink.700");
  const cardBorder = useColorModeValue("ink.200", "ink.600");
  const unavailableTitle = useColorModeValue("ink.600", "ink.300");
  const unavailableDescription = useColorModeValue("ink.500", "ink.400");
  const unavailableCtaBorder = useColorModeValue("ink.300", "ink.500");
  const unavailableCtaHover = useColorModeValue("ink.100", "whiteAlpha.100");

  const handleServiceClick = async (path: string) => {
    if (isLoading) return;
    router.push(path);
  };

  const services = useMemo(
    () =>
      [
        { id: "nmt" as ServiceId, icon: IoLanguageOutline, path: servicePath("nmt") },
        { id: "asr" as ServiceId, icon: FaMicrophone, path: servicePath("asr") },
        { id: "tts" as ServiceId, icon: IoVolumeHighOutline, path: servicePath("tts") },
        { id: "llm" as ServiceId, icon: IoSparklesOutline, path: servicePath("llm") },
        { id: "pipeline" as ServiceId, icon: DoubleMicrophoneIcon, path: servicePath("pipeline") },
        { id: "ocr" as ServiceId, icon: IoDocumentTextOutline, path: servicePath("ocr") },
        { id: "transliteration" as ServiceId, icon: IoSwapHorizontalOutline, path: servicePath("transliteration") },
        { id: "language-detection" as ServiceId, icon: IoGlobeOutline, path: servicePath("language-detection") },
        { id: "speaker-diarization" as ServiceId, icon: IoPeopleOutline, path: servicePath("speaker-diarization") },
        { id: "language-diarization" as ServiceId, icon: IoLanguageOutline, path: servicePath("language-diarization") },
        { id: "audio-language-detection" as ServiceId, icon: IoRadioOutline, path: servicePath("audio-language-detection") },
        { id: "ner" as ServiceId, icon: IoPricetagOutline, path: servicePath("ner") },
      ]
        .filter((service) => {
          if (isGuest) {
            if (guestServicesLoading) return false;
            if (!(allowedServiceIds?.has(service.id) ?? false)) return false;
          }
          if (inferenceTypesLoading && enabledServiceIds.size === 0) return false;
          if (!enabledServiceIds.has(service.id)) return false;
          return true;
        })
        .map((s) => ({
          ...s,
          title: getServiceTitle(s.id),
          description: getServiceDescription(s.id),
        })),
    [
      allowedServiceIds,
      enabledServiceIds,
      guestServicesLoading,
      inferenceTypesLoading,
      isGuest,
    ],
  );

  return (
    <>
      <Head>
        <title>{getPlatformName()}</title>
        <meta
          name="description"
          content="Test LLM models with a modern web interface"
        />
      </Head>

      <ContentLayout>
        <VStack spacing={5} w="full" align="stretch">
          <Box w="full">
            <Heading as="h1" size="lg" mb={1}>
              AI Accessibility Studio
            </Heading>
            <Text fontSize="sm" color="ink.600" fontWeight="500" maxW="40rem" lineHeight="1.5">
              {enabledServiceIds.size === 1 && enabledServiceIds.has("llm")
                ? "Test and explore Large Language Models"
                : "Test and explore NLP and LLM models"}
            </Text>
          </Box>

          {!isLoading && !isAuthenticated && (
            <Alert status="info" variant="left-accent" w="full">
              <AlertIcon />
              <AlertDescription fontSize="sm">
                Try <strong>Large Language Model (LLM)</strong> without signing in!
                Anonymous access includes one available LLM service with rate limits.
                Sign in or continue as Guest for broader access.
              </AlertDescription>
            </Alert>
          )}

          <SimpleGrid columns={{ base: 1, md: 2, xl: 3 }} spacing={4} w="full">
            {services.map((service) => {
              const isDisabledForAnonymous =
                !isAuthenticated &&
                !ANONYMOUS_ALLOWED_SERVICE_IDS.has(service.id) &&
                !isLoading;

              const openService = () => {
                if (isDisabledForAnonymous) {
                  showToast({
                    type: "warning",
                    message: "Please login to access other services.",
                  });
                  setTimeout(() => {
                    router.push("/auth?redirect=" + encodeURIComponent(service.path));
                  }, 500);
                  return;
                }
                handleServiceClick(service.path);
              };

              const visuals = getExploreServiceCardVisuals(
                service.id,
                !isDisabledForAnonymous,
              );

              return (
                <Card
                  key={service.id}
                  role="group"
                  bg={isDisabledForAnonymous ? unavailableCardBg : availableCardBg}
                  border="1px"
                  borderColor={cardBorder}
                  borderLeftWidth="4px"
                  borderLeftColor={visuals.accentBorder}
                  overflow="hidden"
                  w="full"
                  minH="196px"
                  display="flex"
                  flexDirection="column"
                  cursor="pointer"
                  onClick={openService}
                  _hover={
                    isDisabledForAnonymous
                      ? undefined
                      : {
                          borderColor: getServiceAccent(service.id, 300),
                          borderLeftColor: visuals.accentBorder,
                        }
                  }
                >
                  <CardHeader pb={1} pt={4} px={5}>
                    <HStack spacing={3} align="center">
                      <Box
                        boxSize={10}
                        borderRadius="md"
                        bg={visuals.iconBg}
                        display="flex"
                        alignItems="center"
                        justifyContent="center"
                        flexShrink={0}
                        transition="background-color 0.15s ease"
                        _groupHover={
                          isDisabledForAnonymous
                            ? undefined
                            : { bg: visuals.iconHoverBg }
                        }
                      >
                        <Icon
                          as={service.icon}
                          boxSize={service.id === "pipeline" ? 6 : 5}
                          color={visuals.iconColor}
                        />
                      </Box>
                      <Heading
                        as="h2"
                        size="sm"
                        lineHeight="1.3"
                        color={isDisabledForAnonymous ? unavailableTitle : "ink.800"}
                      >
                        {service.title}
                      </Heading>
                    </HStack>
                  </CardHeader>
                  <CardBody pt={2} pb={4} px={5} flex={1} display="flex" flexDirection="column">
                    <Text
                      fontSize="sm"
                      color={isDisabledForAnonymous ? unavailableDescription : "ink.600"}
                      noOfLines={3}
                      flex={1}
                      mb={4}
                      lineHeight="1.5"
                    >
                      {service.description}
                    </Text>
                    <Button
                      size="sm"
                      w="full"
                      variant={isDisabledForAnonymous ? "outline" : "solid"}
                      bg={visuals.ctaBg}
                      color={isDisabledForAnonymous ? unavailableTitle : visuals.ctaColor}
                      borderColor={
                        isDisabledForAnonymous ? unavailableCtaBorder : visuals.ctaBorder
                      }
                      _hover={
                        isDisabledForAnonymous
                          ? { bg: unavailableCtaHover }
                          : {
                              bg: visuals.ctaHoverBg,
                              borderColor: visuals.ctaHoverBg,
                            }
                      }
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        openService();
                      }}
                      mt="auto"
                    >
                      {isDisabledForAnonymous ? "Sign in required" : "Try it now"}
                    </Button>
                  </CardBody>
                </Card>
              );
            })}
          </SimpleGrid>
        </VStack>
      </ContentLayout>
    </>
  );
};

export default HomePage;
