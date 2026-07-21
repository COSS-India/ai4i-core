/**
 * Embeddable Explicit Feedback widget (thumbs + thumbs-down detail + API submit).
 *
 * Drop-in usage:
 *   <FeedbackWidget
 *     requestId={correlationId}
 *     modelTaskType="NMT"
 *     modelProvider="..."
 *     modelVersion="..."
 *     originalOutput={translatedText}
 *   />
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  AlertIcon,
  Box,
  HStack,
  Text,
  useToast,
  VStack,
} from "@chakra-ui/react";
import {
  DEFAULT_FEEDBACK_LABELS,
  supportsCorrectedOutput,
} from "../../config/feedbackReasons";
import {
  fetchFeedbackReasons,
  submitFeedback,
} from "../../services/feedbackService";
import type {
  FeedbackModelTaskType,
  FeedbackReason,
  FeedbackResponse,
  FeedbackSubmission,
  FeedbackWidgetAccent,
  FeedbackWidgetLabels,
} from "../../types/feedback";
import FeedbackDetailPanel from "./FeedbackDetailPanel";
import ThumbsControl from "./ThumbsControl";

export interface FeedbackWidgetProps extends FeedbackWidgetAccent {
  requestId: string;
  modelTaskType: FeedbackModelTaskType;
  modelProvider: string;
  modelVersion: string;
  modelId?: string;
  languageInfo?: Array<{ sourceLanguage?: string; targetLanguage?: string }>;
  /** Preloaded model output for corrected-output editing. */
  originalOutput?: string;
  /**
   * Force corrected-output field on/off. Default: on for NMT/ASR/OCR/NER/
   * TRANSLITERATION/TEXT_LANG_DETECTION when originalOutput is provided.
   */
  enableCorrectedOutput?: boolean;
  /** Override copy for branding / localization. */
  labels?: Partial<FeedbackWidgetLabels>;
  /** Disable interaction (e.g. while a new inference is running). */
  disabled?: boolean;
  /** Optional className for host styling / CSS modules. */
  className?: string;
  onSubmitted?: (response: FeedbackResponse) => void;
  onError?: (error: Error) => void;
  /**
   * Override API calls for embedding outside the portal (custom base URL,
   * auth, or mocks). Defaults to platform POST/GET feedback endpoints.
   */
  api?: {
    submit?: (payload: FeedbackSubmission) => Promise<FeedbackResponse>;
    fetchReasons?: (
      modelTaskType: FeedbackModelTaskType,
    ) => Promise<{ reasons: FeedbackReason[]; fromFallback: boolean }>;
  };
}

type WidgetPhase = "idle" | "detail" | "done";

const FeedbackWidget: React.FC<FeedbackWidgetProps> = ({
  requestId,
  modelTaskType,
  modelProvider,
  modelVersion,
  modelId,
  languageInfo,
  originalOutput = "",
  enableCorrectedOutput,
  labels: labelOverrides,
  disabled = false,
  className,
  colorScheme = "orange",
  accentColor,
  detailPanelBg,
  onSubmitted,
  onError,
  api,
}) => {
  const toast = useToast();
  const labels = useMemo(
    () => ({ ...DEFAULT_FEEDBACK_LABELS, ...labelOverrides }),
    [labelOverrides],
  );

  const submitFn = api?.submit ?? submitFeedback;
  const fetchReasonsFn = api?.fetchReasons ?? fetchFeedbackReasons;

  const showCorrectedOutput =
    enableCorrectedOutput ??
    (supportsCorrectedOutput(modelTaskType) && originalOutput.length > 0);

  const [phase, setPhase] = useState<WidgetPhase>("idle");
  const [rating, setRating] = useState<"POSITIVE" | "NEGATIVE" | null>(null);
  const [detailOpen, setDetailOpen] = useState(true);
  const [reasons, setReasons] = useState<FeedbackReason[]>([]);
  const [reasonsLoading, setReasonsLoading] = useState(false);
  const [reasonsFromFallback, setReasonsFromFallback] = useState(false);
  const [selectedReasons, setSelectedReasons] = useState<string[]>([]);
  const [comments, setComments] = useState("");
  const [correctedOutput, setCorrectedOutput] = useState(originalOutput);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Reset when the underlying inference request changes.
  useEffect(() => {
    setPhase("idle");
    setRating(null);
    setDetailOpen(true);
    setSelectedReasons([]);
    setComments("");
    setCorrectedOutput(originalOutput);
    setIsSubmitting(false);
    setSubmitError(null);
  }, [requestId, originalOutput]);

  // Prefetch reasons when opening the negative detail panel.
  useEffect(() => {
    if (phase !== "detail") return;
    let cancelled = false;
    setReasonsLoading(true);
    fetchReasonsFn(modelTaskType)
      .then(({ reasons: loaded, fromFallback }) => {
        if (cancelled) return;
        setReasons(loaded);
        setReasonsFromFallback(fromFallback);
      })
      .finally(() => {
        if (!cancelled) setReasonsLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // api.fetchReasons identity may change each render; task type + phase drive reloads.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fetchReasonsFn omitted intentionally
  }, [phase, modelTaskType]);

  const postFeedback = useCallback(
    async (nextRating: "POSITIVE" | "NEGATIVE", opts?: { skipDetail?: boolean }) => {
      setIsSubmitting(true);
      setSubmitError(null);
      try {
        const isNegative = nextRating === "NEGATIVE";
        const includeDetail = isNegative && !opts?.skipDetail;
        const trimmedCorrection = correctedOutput.trim();
        const hasEditedCorrection =
          showCorrectedOutput &&
          trimmedCorrection.length > 0 &&
          trimmedCorrection !== originalOutput.trim();

        const payload = {
          requestId,
          modelTaskType,
          feedbackType: "THUMBS" as const,
          rating: nextRating,
          modelProvider,
          modelVersion,
          modelId,
          languageInfo,
          ...(includeDetail
            ? {
                reasons: selectedReasons.length ? selectedReasons : undefined,
                comments: comments.trim() || undefined,
                correctedOutput: hasEditedCorrection
                  ? trimmedCorrection
                  : undefined,
              }
            : {}),
        };

        const response = await submitFn(payload);
        setPhase("done");
        setRating(nextRating);
        onSubmitted?.(response);
        toast({
          status: "success",
          title:
            nextRating === "POSITIVE"
              ? labels.thanksPositive
              : labels.thanksNegative,
          duration: 2500,
          isClosable: true,
        });
      } catch (err) {
        const error =
          err instanceof Error ? err : new Error("Failed to submit feedback");
        setSubmitError(error.message);
        onError?.(error);
        toast({
          status: "error",
          title: "Could not submit feedback",
          description: error.message,
          duration: 4000,
          isClosable: true,
        });
      } finally {
        setIsSubmitting(false);
      }
    },
    [
      requestId,
      modelTaskType,
      modelProvider,
      modelVersion,
      modelId,
      languageInfo,
      selectedReasons,
      comments,
      correctedOutput,
      originalOutput,
      showCorrectedOutput,
      onSubmitted,
      onError,
      toast,
      labels.thanksPositive,
      labels.thanksNegative,
      submitFn,
    ],
  );

  const handlePositive = () => {
    if (disabled || isSubmitting || phase === "done") return;
    setRating("POSITIVE");
    void postFeedback("POSITIVE");
  };

  const handleNegative = () => {
    if (disabled || isSubmitting || phase === "done") return;
    setRating("NEGATIVE");
    setPhase("detail");
    setDetailOpen(true);
  };

  const handleSubmitDetail = () => {
    if (selectedReasons.length === 0) return;
    void postFeedback("NEGATIVE");
  };

  const handleSkip = () => {
    void postFeedback("NEGATIVE", { skipDetail: true });
  };

  if (!requestId || !modelProvider || !modelVersion) {
    return null;
  }

  return (
    <Box
      className={className}
      w="full"
      style={
        {
          ["--fb-accent" as string]: accentColor || undefined,
        } as React.CSSProperties
      }
      data-feedback-widget
      data-task-type={modelTaskType}
    >
      <VStack align="stretch" spacing={3}>
        {phase === "done" ? (
          <HStack
            justify="space-between"
            px={1}
            py={2}
            borderTop="1px solid"
            borderColor="gray.100"
          >
            <Text fontSize="sm" color="gray.600" fontWeight="medium">
              {rating === "POSITIVE"
                ? labels.thanksPositive
                : labels.thanksNegative}
            </Text>
            <HStack spacing={2}>
              <ThumbsControl
                rating={rating}
                disabled
                accentColor={accentColor}
                colorScheme={colorScheme}
                rateHelpfulLabel={labels.rateHelpful}
                rateNotHelpfulLabel={labels.rateNotHelpful}
                onPositive={() => undefined}
                onNegative={() => undefined}
              />
            </HStack>
          </HStack>
        ) : (
          <>
            <HStack
              justify="space-between"
              px={1}
              py={2}
              borderTop="1px solid"
              borderColor="gray.100"
            >
              <Text fontSize="sm" color="gray.600" fontWeight="medium">
                {labels.prompt}
              </Text>
              <HStack spacing={2}>
                <ThumbsControl
                  rating={rating}
                  disabled={disabled || isSubmitting}
                  accentColor={accentColor}
                  colorScheme={colorScheme}
                  rateHelpfulLabel={labels.rateHelpful}
                  rateNotHelpfulLabel={labels.rateNotHelpful}
                  onPositive={handlePositive}
                  onNegative={handleNegative}
                />
              </HStack>
            </HStack>

            {phase === "detail" && (
              <FeedbackDetailPanel
                isOpen={detailOpen}
                title={labels.detailTitle}
                reasons={reasons}
                selectedReasons={selectedReasons}
                comments={comments}
                correctedOutput={correctedOutput}
                showCorrectedOutput={showCorrectedOutput}
                correctedOutputLabel={labels.correctedOutputLabel}
                correctedOutputPlaceholder={labels.correctedOutputPlaceholder}
                commentPlaceholder={labels.commentPlaceholder}
                submitLabel={labels.submit}
                skipLabel={labels.skip}
                reasonsLoading={reasonsLoading}
                reasonsHint={
                  reasonsFromFallback ? labels.reasonsError : null
                }
                isSubmitting={isSubmitting}
                accentColor={accentColor}
                colorScheme={colorScheme}
                detailPanelBg={detailPanelBg}
                onToggle={() => setDetailOpen((open) => !open)}
                onReasonsChange={setSelectedReasons}
                onCommentsChange={setComments}
                onCorrectedOutputChange={setCorrectedOutput}
                onSubmit={handleSubmitDetail}
                onSkip={handleSkip}
              />
            )}
          </>
        )}

        {submitError && (
          <Alert status="error" borderRadius="md" py={2}>
            <AlertIcon />
            <Text fontSize="sm">{submitError}</Text>
          </Alert>
        )}
      </VStack>
    </Box>
  );
};

export default FeedbackWidget;
