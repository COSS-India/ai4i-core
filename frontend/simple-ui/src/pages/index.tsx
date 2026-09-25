import {
  Alert,
  AlertDescription,
  AlertIcon,
  Badge,
  Box,
  Button,
  Card,
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
import ManagementPageHeader from "../components/common/ManagementPageHeader";
import {
  getExploreServiceCardVisuals,
  getServiceDescription,
  getServiceShortCode,
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
        <VStack spacing={0} w="full" align="stretch">
          <ManagementPageHeader
            title="AI Accessibility Studio"
            description={
              enabledServiceIds.size === 1 && enabledServiceIds.has("llm")
                ? "Test and explore Large Language Models"
                : "Test and explore NLP and LLM models"
            }
          />
          <VStack spacing={5} w="full" align="stretch">

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

          <SimpleGrid columns={{ base: 1, md: 2, lg: 3 }} spacing={5} w="full" alignItems="stretch">
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
              const shortCode = getServiceShortCode(service.id);

              return (
                <Card
                  key={service.id}
                  role="group"
                  bg={isDisabledForAnonymous ? unavailableCardBg : availableCardBg}
                  border="1px solid"
                  borderColor={cardBorder}
                  borderTopWidth="3px"
                  borderTopColor={visuals.accentBorder}
                  borderRadius="md"
                  boxShadow="xs"
                  overflow="hidden"
                  w="full"
                  h="full"
                  display="flex"
                  flexDirection="column"
                  cursor="pointer"
                  transition="border-color 0.15s ease, box-shadow 0.15s ease"
                  onClick={openService}
                  _hover={
                    isDisabledForAnonymous
                      ? undefined
                      : {
                          borderColor: visuals.accentBorder,
                          boxShadow: "sm",
                        }
                  }
                >
                  <VStack align="stretch" spacing={4} p={5} flex={1}>
                    <HStack spacing={3} align="flex-start">
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
                        <Icon as={service.icon} boxSize={5} color={visuals.iconColor} />
                      </Box>
                      <Heading
                        as="h2"
                        flex={1}
                        minW={0}
                        fontSize="md"
                        fontWeight="700"
                        lineHeight="1.35"
                        color={isDisabledForAnonymous ? unavailableTitle : "ink.800"}
                      >
                        {service.title}
                      </Heading>
                      {shortCode && (
                        <Badge
                          bg={visuals.badgeBg}
                          color={visuals.badgeColor}
                          fontSize="xs"
                          fontWeight="600"
                          letterSpacing="0.04em"
                          textTransform="uppercase"
                          borderRadius="sm"
                          px={2}
                          py={0.5}
                          flexShrink={0}
                        >
                          {shortCode}
                        </Badge>
                      )}
                    </HStack>
                    <Text
                      fontSize="sm"
                      color={isDisabledForAnonymous ? unavailableDescription : "ink.600"}
                      noOfLines={3}
                      flex={1}
                      lineHeight="tall"
                    >
                      {service.description}
                    </Text>
                    <Button
                      size="sm"
                      w="full"
                      mt="auto"
                      variant={isDisabledForAnonymous ? "outline" : "ghost"}
                      bg={visuals.ctaBg}
                      color={isDisabledForAnonymous ? unavailableTitle : visuals.ctaColor}
                      fontWeight="600"
                      borderRadius="md"
                      borderColor={
                        isDisabledForAnonymous ? unavailableCtaBorder : visuals.ctaBorder
                      }
                      _hover={
                        isDisabledForAnonymous
                          ? { bg: unavailableCtaHover }
                          : { bg: visuals.ctaHoverBg }
                      }
                      _focusVisible={{ boxShadow: "outline" }}
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        openService();
                      }}
                    >
                      {isDisabledForAnonymous ? "Sign in required" : "Try it now →"}
                    </Button>
                  </VStack>
                </Card>
              );
            })}
          </SimpleGrid>
          </VStack>
        </VStack>
      </ContentLayout>
    </>
  );
};

export default HomePage;
