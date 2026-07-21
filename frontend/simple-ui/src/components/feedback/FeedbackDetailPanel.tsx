import React from "react";
import {
  Box,
  Button,
  Checkbox,
  CheckboxGroup,
  Collapse,
  FormControl,
  FormLabel,
  HStack,
  IconButton,
  Spinner,
  Stack,
  Text,
  Textarea,
  VStack,
} from "@chakra-ui/react";
import { FaChevronDown, FaChevronUp } from "react-icons/fa";
import type { FeedbackReason } from "../../types/feedback";

export interface FeedbackDetailPanelProps {
  isOpen: boolean;
  title: string;
  reasons: FeedbackReason[];
  selectedReasons: string[];
  comments: string;
  correctedOutput: string;
  showCorrectedOutput: boolean;
  correctedOutputLabel: string;
  correctedOutputPlaceholder: string;
  commentPlaceholder: string;
  submitLabel: string;
  skipLabel: string;
  reasonsLoading: boolean;
  reasonsHint?: string | null;
  isSubmitting: boolean;
  accentColor?: string;
  colorScheme?: string;
  detailPanelBg?: string;
  onToggle: () => void;
  onReasonsChange: (codes: string[]) => void;
  onCommentsChange: (value: string) => void;
  onCorrectedOutputChange: (value: string) => void;
  onSubmit: () => void;
  onSkip: () => void;
}

const FeedbackDetailPanel: React.FC<FeedbackDetailPanelProps> = ({
  isOpen,
  title,
  reasons,
  selectedReasons,
  comments,
  correctedOutput,
  showCorrectedOutput,
  correctedOutputLabel,
  correctedOutputPlaceholder,
  commentPlaceholder,
  submitLabel,
  skipLabel,
  reasonsLoading,
  reasonsHint,
  isSubmitting,
  accentColor,
  colorScheme = "orange",
  detailPanelBg = "#FFF8F0",
  onToggle,
  onReasonsChange,
  onCommentsChange,
  onCorrectedOutputChange,
  onSubmit,
  onSkip,
}) => {
  const canSubmit = selectedReasons.length > 0 && !isSubmitting;
  const focusBorder = accentColor || `${colorScheme}.400`;

  return (
    <Box
      borderRadius="md"
      border="1px solid"
      borderColor="blackAlpha.100"
      bg={detailPanelBg}
      overflow="hidden"
    >
      <HStack
        as="button"
        type="button"
        w="full"
        px={4}
        py={3}
        justify="space-between"
        onClick={onToggle}
        aria-expanded={isOpen}
        _hover={{ bg: "blackAlpha.50" }}
      >
        <HStack spacing={2}>
          <Text fontSize="lg" lineHeight={1} aria-hidden>
            👎
          </Text>
          <Text fontWeight="semibold" fontSize="sm" color="gray.800">
            {title}
          </Text>
        </HStack>
        <IconButton
          aria-label={isOpen ? "Collapse feedback panel" : "Expand feedback panel"}
          icon={isOpen ? <FaChevronUp /> : <FaChevronDown />}
          size="xs"
          variant="ghost"
          pointerEvents="none"
          tabIndex={-1}
        />
      </HStack>

      <Collapse in={isOpen} animateOpacity>
        <VStack align="stretch" spacing={4} px={4} pb={4} pt={1}>
          {reasonsLoading ? (
            <HStack spacing={2} color="gray.600">
              <Spinner size="sm" />
              <Text fontSize="sm">Loading reasons…</Text>
            </HStack>
          ) : (
            <CheckboxGroup
              value={selectedReasons}
              onChange={(values) => onReasonsChange(values as string[])}
            >
              <Stack spacing={2}>
                {reasons.map((reason) => (
                  <Checkbox
                    key={reason.code}
                    value={reason.code}
                    colorScheme={accentColor ? undefined : colorScheme}
                    sx={
                      accentColor
                        ? {
                            "[data-checked]": {
                              borderColor: accentColor,
                              background: accentColor,
                            },
                          }
                        : undefined
                    }
                    alignItems="flex-start"
                  >
                    <Box>
                      <Text fontSize="sm" fontWeight="medium" color="gray.800">
                        {reason.label}
                      </Text>
                      {reason.description && (
                        <Text fontSize="xs" color="gray.500" mt={0.5}>
                          {reason.description}
                        </Text>
                      )}
                    </Box>
                  </Checkbox>
                ))}
              </Stack>
            </CheckboxGroup>
          )}

          {reasonsHint && (
            <Text fontSize="xs" color="gray.500">
              {reasonsHint}
            </Text>
          )}

          {selectedReasons.length > 0 && (
            <FormControl>
              <Textarea
                value={comments}
                onChange={(e) => onCommentsChange(e.target.value)}
                placeholder={commentPlaceholder}
                size="sm"
                bg="white"
                borderColor="gray.200"
                focusBorderColor={focusBorder}
                rows={2}
                resize="vertical"
              />
            </FormControl>
          )}

          {showCorrectedOutput && selectedReasons.length > 0 && (
            <FormControl>
              <FormLabel fontSize="sm" mb={1} color="gray.700">
                {correctedOutputLabel}
              </FormLabel>
              <Textarea
                value={correctedOutput}
                onChange={(e) => onCorrectedOutputChange(e.target.value)}
                placeholder={correctedOutputPlaceholder}
                size="sm"
                bg="white"
                borderColor="gray.200"
                focusBorderColor={focusBorder}
                rows={4}
                resize="vertical"
                fontFamily="mono"
              />
            </FormControl>
          )}

          <HStack justify="flex-end" spacing={3} pt={1}>
            <Button
              size="sm"
              variant="ghost"
              onClick={onSkip}
              isDisabled={isSubmitting}
            >
              {skipLabel}
            </Button>
            <Button
              size="sm"
              colorScheme={accentColor ? undefined : colorScheme}
              bg={accentColor}
              _hover={accentColor ? { opacity: 0.9 } : undefined}
              onClick={onSubmit}
              isLoading={isSubmitting}
              isDisabled={!canSubmit}
            >
              {submitLabel}
            </Button>
          </HStack>
        </VStack>
      </Collapse>
    </Box>
  );
};

export default FeedbackDetailPanel;
