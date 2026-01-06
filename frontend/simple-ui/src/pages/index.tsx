// pages/index.tsx  (or wherever your HomePage lives)
import {
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
import { useFeatureFlag } from "../hooks/useFeatureFlag";
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
  const { isAuthenticated, isLoading } = useAuth();
  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");

  const handleServiceClick = async (path: string) => {
    if (isLoading) return;
    if (!isAuthenticated) {
      if (typeof window !== "undefined") {
        sessionStorage.setItem("redirectAfterAuth", path);
      }
      router.push("/auth");
      return;
    }
    router.push(path);
  };

  // Feature flags for each service
  const asrEnabled = useFeatureFlag({ flagName: "asr-enabled" });
  const ttsEnabled = useFeatureFlag({ flagName: "tts-enabled" });
  const nmtEnabled = useFeatureFlag({ flagName: "nmt-enabled" });
  const llmEnabled = useFeatureFlag({ flagName: "llm-enabled" });
  const pipelineEnabled = useFeatureFlag({ flagName: "pipeline-enabled" });
  const modelManagementEnabled = useFeatureFlag({ flagName: "model-management-enabled" });
  const ocrEnabled = useFeatureFlag({ flagName: "ocr-enabled" });
  const transliterationEnabled = useFeatureFlag({ flagName: "transliteration-enabled" });
  const languageDetectionEnabled = useFeatureFlag({ flagName: "language-detection-enabled" });
  const speakerDiarizationEnabled = useFeatureFlag({ flagName: "speaker-diarization-enabled" });
  const languageDiarizationEnabled = useFeatureFlag({ flagName: "language-diarization-enabled" });
  const audioLanguageDetectionEnabled = useFeatureFlag({ flagName: "audio-language-detection-enabled" });
  const nerEnabled = useFeatureFlag({ flagName: "ner-enabled" });

const services = [
  {
    id: "asr",
    title: "Automatic Speech Recognition (ASR)",
    description: "Convert spoken audio into accurate text in multiple Indic languages.",
    icon: FaMicrophone,
    path: "/asr",
    color: "orange",
    enabled: asrEnabled.isEnabled,
  },
  {
    id: "tts",
    title: "Text-to-Speech (TTS)",
    description: "Generate natural-sounding speech from text in various Indic languages.",
    icon: IoVolumeHighOutline,
    path: "/tts",
    color: "blue",
    enabled: ttsEnabled.isEnabled,
  },
  {
    id: "nmt",
    title: "Neural Machine Translation (NMT)",
    description: "Translate text instantly between 22+ Indic languages.",
    icon: IoLanguageOutline,
    path: "/nmt",
    color: "green",
    enabled: nmtEnabled.isEnabled,
  },
  {
    id: "llm",
    title: "Large Language Model (LLM)",
    description: "Use advanced AI models for contextual translation and language tasks.",
    icon: IoSparklesOutline,
    path: "/llm",
    color: "pink",
    enabled: llmEnabled.isEnabled,
  },
  {
    id: "pipeline",
    title: "Speech to Speech\nPipeline",
    description: "Create workflows by chaining together multiple AI language services.",
    icon: DoubleMicrophoneIcon,
    path: "/pipeline",
    color: "purple",
    enabled: pipelineEnabled.isEnabled,
  },
  {
    id: "ocr",
    title: "Optical Character Recognition (OCR)",
    description: "Extract editable text from images, scanned documents, and photos.",
    icon: IoDocumentTextOutline,
    path: "/ocr",
    color: "indigo",
    enabled: ocrEnabled.isEnabled,
  },
  {
    id: "transliteration",
    title: "Transliteration Service",
    description: "Convert text from one script to another while keeping pronunciation intact.",
    icon: IoSwapHorizontalOutline,
    path: "/transliteration",
    color: "cyan",
    enabled: transliterationEnabled.isEnabled,
  },
  {
    id: "language-detection",
    title: "Language Detection",
    description: "Automatically identify the language and script of any given text.",
    icon: IoGlobeOutline,
    path: "/language-detection",
    color: "teal",
    enabled: languageDetectionEnabled.isEnabled,
  },
  {
    id: "speaker-diarization",
    title: "Speaker Diarization",
    description: "Separate conversations into segments based on who is speaking.",
    icon: IoPeopleOutline,
    path: "/speaker-diarization",
    color: "red",
    enabled: speakerDiarizationEnabled.isEnabled,
  },
  {
    id: "language-diarization",
    title: "Language Diarization",
    description: "Identify when language changes occur within spoken audio.",
    icon: IoLanguageOutline,
    path: "/language-diarization",
    color: "yellow",
    enabled: languageDiarizationEnabled.isEnabled,
  },
  {
    id: "audio-language-detection",
    title: "Audio Language Detection",
    description: "Detect the spoken language directly from an audio file.",
    icon: IoRadioOutline,
    path: "/audio-language-detection",
    color: "gray",
    enabled: audioLanguageDetectionEnabled.isEnabled,
  },
  {
    id: "ner",
    title: "Named Entity Recognition (NER)",
    description: "Identify key entities like names, locations, and organizations in text.",
    icon: IoPricetagOutline,
    path: "/ner",
    color: "rose",
    enabled: nerEnabled.isEnabled,
  },
].filter((service) => service.enabled);


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
            <Heading size="lg" fontWeight="bold" color="gray.800" mb={2}>
              AI Accessibility Studio
            </Heading>
            <Text fontSize="sm" color="gray.600" maxW="600px" mx="auto">
              Test and explore NLP and LLM models
            </Text>
          </Box>

          {/* Service Cards Grid */}
          <SimpleGrid
            columns={{ base: 1, sm: 2, md: 3, lg: 4, xl: 6 }}
            spacing={6}
            w="full"
            maxW="1800px"
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
                  borderColor: getColor(service, 300),
                }}
                transition="all 0.3s ease"
                w={{ base: "100%", sm: "100%", md: "100%", lg: "100%", xl: "100%" }}
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
                  bgGradient={`linear(to-r, ${getColor(service, 400)}, ${getColor(service, 600)})`}
                />

                <CardHeader textAlign="center" pb={2} pt={4} px={4} flexShrink={0}>
                  <VStack spacing={2} align="center" w="full">
                    <Box
                      p={3}
                      borderRadius="full"
                      bg={getColor(service, 50)}
                      _dark={{ bg: getColor(service, 600) }}
                      display="flex"
                      alignItems="center"
                      justifyContent="center"
                      flexShrink={0}
                    >
                      <Icon as={service.icon} boxSize={7} color={getColor(service, 600)} />
                    </Box>
                    <Heading
                      size="sm"
                      color="gray.800"
                      fontWeight="semibold"
                      textAlign="center"
                      noOfLines={3}
                      wordBreak="break-word"
                      whiteSpace="pre-line"
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
                    color="gray.600"
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
                    bg={getColor(service, 300)}
                    borderColor={getColor(service, 300)}
                    borderWidth="1px"
                    color="black"
                    _hover={{
                      transform: "translateY(-2px)",
                      boxShadow: "md",
                      bg: getColor(service, 400),
                      color: "black",
                      borderColor: getColor(service, 400),
                    }}
                    onClick={(e) => {
                      e.preventDefault();
                      handleServiceClick(service.path);
                    }}
                    transition="all 0.2s"
                    flexShrink={0}
                    mt="auto"
                  >
                    Try it now
                  </Button>
                </CardBody>
              </Card>
            ))}
          </SimpleGrid>
        </VStack>
      </ContentLayout>
    </>
  );
};

export default HomePage;
