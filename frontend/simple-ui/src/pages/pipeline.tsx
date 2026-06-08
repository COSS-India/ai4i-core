// Pipeline service page for Speech-to-Speech translation

import { Alert, AlertDescription, AlertIcon, Button } from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/router";
import React, { useState } from "react";
import PipelineAudioSection from "../components/pipeline/PipelineAudioSection";
import PipelineConfigPanel from "../components/pipeline/PipelineConfigPanel";
import PipelineResultView from "../components/pipeline/PipelineResultView";
import {
  RequestContainer,
  ResponseContainer,
  ServicePageLayout,
} from "../components/service-page";
import { getServicePageDefaults } from "../config/servicePageConfig";
import { useAuth } from "../hooks/useAuth";
import { usePipeline } from "../hooks/usePipeline";
import { useToastWithDeduplication } from "../hooks/useToastWithDeduplication";
import { listASRServices, ASRServiceDetails } from "../services/asrService";
import { listNMTServices } from "../services/nmtService";
import { listTTSServices, TTSServiceDetailsResponse } from "../services/ttsService";

const pageDefaults = getServicePageDefaults("pipeline");

const PipelinePage: React.FC = () => {
  const toast = useToastWithDeduplication();
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const [sourceLanguage, setSourceLanguage] = useState("");
  const [targetLanguage, setTargetLanguage] = useState("");
  const [asrServiceId, setAsrServiceId] = useState("");
  const [nmtServiceId, setNmtServiceId] = useState("");
  const [ttsServiceId, setTtsServiceId] = useState("");
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);

  const {
    isLoading,
    result,
    isRecording,
    timer,
    pendingAudio,
    startRecording,
    stopRecording,
    processUploadedAudio,
    setProcessRecordedAudioCallback,
    runPipeline,
    clearInput,
  } = usePipeline();

  const { data: asrServices } = useQuery<ASRServiceDetails[]>({
    queryKey: ["asr-services"],
    queryFn: listASRServices,
    staleTime: 5 * 60 * 1000,
  });

  const { data: nmtServices } = useQuery({
    queryKey: ["nmt-services", isAuthenticated],
    queryFn: listNMTServices,
    staleTime: 5 * 60 * 1000,
  });

  const { data: ttsServices } = useQuery<TTSServiceDetailsResponse[]>({
    queryKey: ["tts-services"],
    queryFn: listTTSServices,
    staleTime: 5 * 60 * 1000,
  });

  const hasRequiredConfig = () =>
    !!sourceLanguage?.trim() &&
    !!targetLanguage?.trim() &&
    !!asrServiceId?.trim() &&
    !!nmtServiceId?.trim() &&
    !!ttsServiceId?.trim();

  const ensureConfigOrToast = () => {
    if (!sourceLanguage?.trim() || !targetLanguage?.trim()) {
      toast({
        title: "Language Required",
        description:
          "Please select both source and target languages before recording or uploading audio.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return false;
    }
    if (!asrServiceId?.trim() || !nmtServiceId?.trim() || !ttsServiceId?.trim()) {
      toast({
        title: "Service Selection Required",
        description:
          "Please select ASR, NMT, and TTS services before recording or uploading audio.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return false;
    }
    return true;
  };

  const canRunPipeline = hasRequiredConfig() && !isLoading;
  const canSubmit = hasRequiredConfig() && !!pendingAudio && !isLoading;

  const handleRecordClick = async () => {
    if (!ensureConfigOrToast()) return;

    if (isRecording) {
      stopRecording();
    } else {
      setUploadedFileName(null);
      setProcessRecordedAudioCallback(
        sourceLanguage,
        targetLanguage,
        asrServiceId,
        nmtServiceId,
        ttsServiceId
      );
      startRecording();
    }
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    if (!ensureConfigOrToast()) {
      event.target.value = "";
      return;
    }

    try {
      setUploadedFileName(file.name);
      await processUploadedAudio(
        file,
        sourceLanguage,
        targetLanguage,
        asrServiceId,
        nmtServiceId,
        ttsServiceId
      );
    } catch (error) {
      console.error("Pipeline upload error:", error);
    }

    event.target.value = "";
  };

  const handleRunPipeline = () => {
    if (!ensureConfigOrToast()) return;
    if (!pendingAudio) {
      toast({
        title: "Audio Required",
        description: "Please record or upload an audio file before running the pipeline.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    runPipeline(
      sourceLanguage,
      targetLanguage,
      asrServiceId,
      nmtServiceId,
      ttsServiceId
    );
  };

  const handleClearAudio = () => {
    setUploadedFileName(null);
    clearInput();
  };

  return (
    <ServicePageLayout
      serviceId="pipeline"
      headingSize="lg"
      headTitle="Speech to Speech | AI4Inclusion Console"
      headDescription="Transform spoken input into translated speech output using chained AI models"
      headerExtra={
        <Button
          size="sm"
          variant="outline"
          colorScheme="orange"
          onClick={() => router.push("/pipeline-builder")}
          ml={4}
        >
          Customize Pipeline
        </Button>
      }
      banner={
        <Alert status="info" borderRadius="md" alignItems="center" w="full" maxW="1200px" mx="auto">
          <AlertIcon />
          <AlertDescription>
            The pipeline chains Automatic Speech Recognition (ASR), Neural Machine Translation
            (NMT), and Text-to-Speech (TTS) services to convert speech from one language to another.
          </AlertDescription>
        </Alert>
      }
      requestPanel={
        <RequestContainer
          inputType="custom"
          helperText={pageDefaults.helperText}
          submitButton={{
            label: pageDefaults.submitLabel,
            loadingLabel: pageDefaults.submitLoadingLabel,
            onClick: handleRunPipeline,
            isLoading: isLoading,
            isDisabled: !canSubmit,
          }}
        >
          <PipelineConfigPanel
            sourceLanguage={sourceLanguage}
            targetLanguage={targetLanguage}
            asrServiceId={asrServiceId}
            nmtServiceId={nmtServiceId}
            ttsServiceId={ttsServiceId}
            asrServices={asrServices}
            nmtServices={nmtServices}
            ttsServices={ttsServices}
            disabled={isLoading}
            onSourceLanguageChange={setSourceLanguage}
            onTargetLanguageChange={setTargetLanguage}
            onAsrServiceChange={setAsrServiceId}
            onNmtServiceChange={setNmtServiceId}
            onTtsServiceChange={setTtsServiceId}
          />
          <PipelineAudioSection
            isRecording={isRecording}
            timer={timer}
            pendingAudio={pendingAudio}
            uploadedFileName={uploadedFileName}
            canRunPipeline={canRunPipeline}
            isLoading={isLoading}
            onRecordClick={handleRecordClick}
            onFileUpload={handleFileUpload}
            onClear={handleClearAudio}
          />
        </RequestContainer>
      }
      responsePanel={
        <ResponseContainer
          fetching={isLoading}
          fetchingLabel="Processing pipeline..."
          fetched={!!result}
          hasResult={!!result}
          result={result ? <PipelineResultView result={result} /> : undefined}
        />
      }
    />
  );
};

export default PipelinePage;
