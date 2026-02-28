// pages/index.tsx  (or wherever your HomePage lives)
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
  Icon,
  SimpleGrid,
  Text,
  VStack,
  useColorModeValue,
} from "@chakra-ui/react";
import Head from "next/head";
import { useRouter } from "next/router";
import React from "react";
import { useToastWithDeduplication } from "../hooks/useToastWithDeduplication";
import { FaMicrophone } from "react-icons/fa";
import {
  IoGitMergeOutline,
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
import { useAuth } from "../hooks/useAuth";
import { useFeatureFlagsBulk, ALL_UI_FEATURE_FLAG_NAMES } from "../hooks/useFeatureFlag";
import DoubleMicrophoneIcon from "../components/common/DoubleMicrophoneIcon";

const safeColorMap:any = {
  asr: { // Coral → Pastel Coral
    50:  "#FFE9E2",
    300: "#FFB8A4",
    400: "#FF9C86",
    600: "#FF7A61",
  },

  tts: { // Royal Blue → Pastel Blue
    50:  "#EAF0FF",
    300: "#B3C7FF",
    400: "#8CAEFF",
    600: "#668FFF",
  },

  nmt: { // Emerald → Pastel Mint
    50:  "#E7FAF1",
    300: "#B3EFD4",
    400: "#90E6C0",
    600: "#6AD2A7",
  },

  llm: { // Magenta → Pastel Pink/Magenta
    50:  "#FFE6FA",
    300: "#FFB3EB",
    400: "#FF8CDE",
    600: "#F061C8",
  },

  pipeline: { // Purple → Pastel Lilac
    50:  "#F8F0FA",
    300: "#E4C9EE",
    400: "#D8AFE8",
    600: "#C08BD8",
  },

  ocr: { // Teal → Pastel Aqua
    50:  "#E5F7F7",
    300: "#B5E8E8",
    400: "#90DDDD",
    600: "#6BC7C7",
  },

  transliteration: { // Turquoise → Pastel Turquoise
    50:  "#E8FCFA",
    300: "#B5F3EC",
    400: "#8DEBDD",
    600: "#6BD2C1",
  },

  "language-detection": { // Crimson → Pastel Red
    50:  "#FFE9EE",
    300: "#FFBBC8",
    400: "#FF9EAF",
    600: "#FF7A8F",
  },

  "speaker-diarization": { // Amber → Pastel Yellow/Amber
    50:  "#FFF9E6",
    300: "#FEE5A8",
    400: "#FFDA7A",
    600: "#F5C554",
  },

  "language-diarization": { // Lime → Pastel Lime Green
    50:  "#F3FFE8",
    300: "#D4FFAA",
    400: "#C0FF85",
    600: "#99F45A",
  },

  "audio-language-detection": { // Replace gray → Pastel Electric Blue
    50:  "#E7F7FF",
    300: "#B3E4FF",
    400: "#89D6FF",
    600: "#63C5FF",
  },

  ner: { // Indigo → Pastel Indigo/Violet
    50:  "#F1E8FF",
    300: "#D0BBFF",
    400: "#BA9AFF",
    600: "#9D72FF",
  },
};




const getColor = (service: { id?: string; color?: string }, shade: 50 | 300 | 400 | 600) => {
  if (!service) return undefined;
  const id = service.id ?? "";
  const base = service.color ?? "";

  // prefer safeColorMap hex values (most robust)
  if (safeColorMap[id] && safeColorMap[id][shade]) {
    return safeColorMap[id][shade];
  }

  // fallback to Chakra token string if you have that in your theme (e.g. "blue.400")
  if (base) {
    return `${base}.${shade}`;
  }

  // final fallback to sensible neutral
  return shade === 50 ? "#F7FAFC" : shade === 300 ? "#CBD5E1" : shade === 400 ? "#A0AEC0" : "#1A202C";
};

const HomePage: React.FC = () => {
  const router = useRouter();
  const toast = useToastWithDeduplication();
  const { isAuthenticated, isLoading } = useAuth();
  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");

  const handleServiceClick = async (path: string, serviceName: string) => {
    if (isLoading) return;
    
    // Navigate to the service (no auth check needed here, handled by button logic)
    router.push(path);
  };

  // Single bulk request shared with Sidebar (same queryKey = one request for whole app)
  const { flags, isLoading: flagsLoading } = useFeatureFlagsBulk({
    flagNames: [...ALL_UI_FEATURE_FLAG_NAMES],
    defaultValue: true,
  });

  const services = [
    {
      id: "asr",
      title: "Automatic Speech Recognition (ASR)",
      description: "Convert spoken audio into accurate, readable text in Indic languages.",
      icon: FaMicrophone,
      path: "/asr",
      color: "orange",
      enabled: flags["asr-enabled"] ?? true,
    },
    {
      id: "tts",
      title: "Text-to-Speech (TTS)",
      description: "Generate natural-sounding speech from text in Indic languages.",
      icon: IoVolumeHighOutline,
      path: "/tts",
      color: "blue",
      enabled: flags["tts-enabled"] ?? true,
    },
    {
      id: "nmt",
      title: "Neural Machine Translation (NMT)",
      description: "Translate text instantly across Indic languages.",
      icon: IoLanguageOutline,
      path: "/nmt",
      color: "green",
      enabled: flags["nmt-enabled"] ?? true,
    },
    {
      id: "llm",
      title: "Large Language Model (LLM)",
      description: "Perform contextual translation and language tasks using advanced AI models.",
      icon: IoSparklesOutline,
      path: "/llm",
      color: "pink",
      enabled: flags["llm-enabled"] ?? true,
    },
    {
      id: "pipeline",
      title: "Speech to Speech\nPipeline",
      description: "Transform spoken input into translated speech output using chained AI models.",
      icon: DoubleMicrophoneIcon,
      path: "/pipeline",
      color: "purple",
      enabled: flags["pipeline-enabled"] ?? true,
    },
    {
      id: "ocr",
      title: "Optical Character Recognition (OCR)",
      description: "Extract editable text from images and scanned documents.",
      icon: IoDocumentTextOutline,
      path: "/ocr",
      color: "indigo",
      enabled: flags["ocr-enabled"] ?? true,
    },
    {
      id: "transliteration",
      title: "Transliteration",
      description: "Convert text from one script to another while preserving pronunciation.",
      icon: IoSwapHorizontalOutline,
      path: "/transliteration",
      color: "cyan",
      enabled: flags["transliteration-enabled"] ?? true,
    },
    {
      id: "language-detection",
      title: "Text Language Detection",
      description: "Automatically identify the language and script of any text input.",
      icon: IoGlobeOutline,
      path: "/language-detection",
      color: "teal",
      enabled: flags["language-detection-enabled"] ?? true,
    },
    {
      id: "speaker-diarization",
      title: "Speaker Diarization",
      description: "Separate audio into segments based on who is speaking.",
      icon: IoPeopleOutline,
      path: "/speaker-diarization",
      color: "red",
      enabled: flags["speaker-diarization-enabled"] ?? true,
    },
    {
      id: "language-diarization",
      title: "Language Diarization",
      description: "Detect language switches in real time within spoken audio.",
      icon: IoLanguageOutline,
      path: "/language-diarization",
      color: "yellow",
      enabled: flags["language-diarization-enabled"] ?? true,
    },
    {
      id: "audio-language-detection",
      title: "Audio Language Detection",
      description: "Identify the spoken language directly from an audio file.",
      icon: IoRadioOutline,
      path: "/audio-language-detection",
      color: "gray",
      enabled: flags["audio-language-detection-enabled"] ?? true,
    },
    {
      id: "ner",
      title: "Named Entity Recognition (NER)",
      description: "Extract key entities like names, locations, and organizations from text.",
      icon: IoPricetagOutline,
      path: "/ner",
      color: "rose",
      enabled: flags["ner-enabled"] ?? true,
    },
  ].filter((service) => flagsLoading || service.enabled);


  return (
    <>
      <Head>
        <title>AI4Inclusion Console</title>
        <meta
          name="description"
          content="Test ASR, TTS, NMT, LLM (GPT OSS 20B), and Speech to Speech microservices with a modern web interface"
        />
      </Head>

      <ContentLayout>
        <VStack spacing={10} w="full" h="full" justify="center" align="center">
          {/* Hero Section */}
          <Box textAlign="center" w="full">
            <Heading size="lg" fontWeight="bold" color="gray.800" mb={2} userSelect="none" cursor="default" tabIndex={-1}>
              AI Accessibility Studio
            </Heading>
            <Text fontSize="sm" color="gray.600" maxW="600px" mx="auto" userSelect="none" cursor="default">
              Test and explore NLP and LLM models
            </Text>
          </Box>

          {/* Anonymous User Info Alert */}
          {!isLoading && !isAuthenticated && (
            <Alert
              status="info"
              variant="left-accent"
              borderRadius="md"
              maxW="1800px"
              w="full"
              mx="auto"
            >
              <AlertIcon />
              <AlertDescription fontSize="sm">
                Try <strong>Neural Machine Translation</strong> without signing in! Please login to access other services{" "}
                
              </AlertDescription>
            </Alert>
          )}

          {/* Service Cards Grid */}
          <SimpleGrid
            columns={{ base: 1, sm: 2, md: 3, lg: 4, xl: 6 }}
            spacing={6}
            w="full"
            maxW="1800px"
            mx="auto"
            justifyItems="center"
          >
            {services.map((service) => {
              // Check if service is disabled for anonymous users
              const isDisabledForAnonymous = !isAuthenticated && service.id !== "nmt" && !isLoading;
              
              return (
              <Card
                key={service.id}
                bg={cardBg}
                border="1px"
                borderColor={cardBorder}
                borderRadius="xl"
                boxShadow="lg"
                overflow="hidden"
                opacity={isDisabledForAnonymous ? 0.5 : 1}
                _hover={{
                  transform: "translateY(-6px)",
                  boxShadow: "2xl",
                  borderColor: getColor(service, 300),
                }}
                transition="all 0.3s ease"
                w={{ base: "100%", sm: "100%", md: "100%", lg: "100%", xl: "100%" }}
                h="260px"
                position="relative"
                display="flex"
                flexDirection="column"
                cursor="pointer"
              >
                {/* Colored top border accent */}
                <Box
                  position="absolute"
                  top={0}
                  left={0}
                  right={0}
                  h="4px"
                  bgGradient={`linear(to-r, ${getColor(service, 400)}, ${getColor(service, 600)})`}
                  opacity={isDisabledForAnonymous ? 0.3 : 1}
                />

                <CardHeader textAlign="center" pb={1} pt={4} px={4} flexShrink={0}>
                  <VStack spacing={2} align="center" w="full">
                    <Box position="relative">
                      <Box
                      // p={3}
                        boxSize={14}
                        borderRadius="full"
                        bg={getColor(service, 50)}
                        _dark={{ bg: getColor(service, 600) }}
                        display="flex"
                        alignItems="center"
                        justifyContent="center"
                        flexShrink={0}
                        overflow="hidden"
                      >
                        <Icon
                          as={service.icon}
                          boxSize={service.id === "pipeline" ? 8 : 7}
                          color={getColor(service, 600)}
                          opacity={isDisabledForAnonymous ? 0.4 : 1}
                        />
                      </Box>
                    </Box>
                    <Heading
                      size="sm"
                      color={isDisabledForAnonymous ? "gray.500" : "gray.800"}
                      fontWeight="semibold"
                      textAlign="center"
                      noOfLines={3}
                      wordBreak="break-word"
                      whiteSpace="pre-line"
                      userSelect="none"
                      cursor="default"
                    >
                      {service.title}
                    </Heading>
                  </VStack>
                </CardHeader>
                <CardBody
                  pt={2}
                  pb={4}
                  px={4}
                  flex={1}
                  display="flex"
                  flexDirection="column"
                  minH={0}
                  overflow="hidden"
                >
                  <Text
                    color={isDisabledForAnonymous ? "gray.400" : "gray.600"}
                    textAlign="center"
                    lineHeight="1"
                    fontSize="sm"
                    flex={1}
                    wordBreak="break-word"
                    overflowWrap="break-word"
                    overflowY="auto"
                    px={1}
                    mb={3}
                    display="flex"
                    alignItems="flex-start"
                    justifyContent="center"
                  >
                    {service.description}
                  </Text>

                  {/* Auth-aware navigation button */}
                  <Button
                    size="md"
                    w="full"
                    fontWeight="semibold"
                    bg={isDisabledForAnonymous ? "gray.200" : getColor(service, 300)}
                    borderColor={isDisabledForAnonymous ? "gray.300" : getColor(service, 300)}
                    borderWidth="1px"
                    color={isDisabledForAnonymous ? "gray.500" : "black"}
                    _hover={{
                      transform: "translateY(-2px)",
                      boxShadow: "md",
                      bg: isDisabledForAnonymous ? "gray.300" : getColor(service, 400),
                      color: isDisabledForAnonymous ? "gray.600" : "black",
                      borderColor: isDisabledForAnonymous ? "gray.400" : getColor(service, 400),
                    }}
                    onClick={(e) => {
                      e.preventDefault();
                      if (isDisabledForAnonymous) {
                        // Show toast and redirect to signup
                        toast({
                          title: "Sign In Required",
                          description: "Please login to access other services.",
                          status: "warning",
                          duration: 4000,
                          isClosable: true,
                          position: "top",
                        });
                        
                        // Store redirect path
                        if (typeof window !== "undefined") {
                          sessionStorage.setItem("redirectAfterAuth", service.path);
                        }
                        
                        // Redirect to auth page
                        setTimeout(() => {
                          router.push("/auth");
                        }, 500);
                      } else {
                        handleServiceClick(service.path, service.title);
                      }
                    }}
                    transition="all 0.2s"
                    flexShrink={0}
                    mt="auto"
                    cursor="pointer"
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
