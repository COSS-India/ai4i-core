import { HamburgerIcon } from "@chakra-ui/icons";
import {
  Box,
  Button,
  Checkbox,
  HStack,
  IconButton,
  Input,
  Text,
  Tooltip,
  useDisclosure,
  VStack,
} from "@chakra-ui/react";
import React, { useMemo, useRef, useState } from "react";
import {
  MAX_THRESHOLD_PERCENT,
  MIN_THRESHOLD_PERCENT,
  validateThresholdDrafts,
  type ThresholdDraftBand,
} from "../../types/notificationAlerts";
import StandardModal from "../common/StandardModal";

interface ThresholdBandsCellProps {
  /** The row's current draft bands — exactly THRESHOLD_BAND_COUNT of them. */
  bands: ThresholdDraftBand[];
  /** Row display name, for the modal title and the inputs' accessible names. */
  rowLabel: string;
  /** Called with the edited set when the user applies the modal. */
  onApply: (bands: ThresholdDraftBand[]) => void;
}

/**
 * The Thresholds cell: one read-only box per band, plus an icon opening a
 * small editor.
 */
const ThresholdBandsCell: React.FC<ThresholdBandsCellProps> = ({
  bands,
  rowLabel,
  onApply,
}) => {
  const { isOpen, onOpen, onClose } = useDisclosure();
  const [editBands, setEditBands] = useState<ThresholdDraftBand[]>(bands);
  const firstInputRef = useRef<HTMLInputElement>(null);

  const validation = useMemo(
    () => validateThresholdDrafts(editBands),
    [editBands],
  );

  const handleOpen = () => {
    // Re-seed from the draft every time, so a previous Cancel leaves nothing
    // behind.
    setEditBands(bands.map((band) => ({ ...band })));
    onOpen();
  };

  const updateBand = (index: number, patch: Partial<ThresholdDraftBand>) => {
    setEditBands((prev) =>
      prev.map((band, i) => (i === index ? { ...band, ...patch } : band)),
    );
  };

  const handleApply = () => {
    const parsed = validation.bands;
    if (!parsed) return;
    // Sorted and normalised on the way out ("07" -> "7"), which is safe to do
    // here because it happens on Apply, not per keystroke — re-sorting while
    // someone was typing would shuffle the fields under the cursor.
    onApply(
      [...parsed]
        .sort((a, b) => a.percentage - b.percentage)
        .map((band) => ({
          percentage: String(band.percentage),
          active: band.active,
        })),
    );
    onClose();
  };

  return (
    <>
      <HStack spacing={2}>
        {/* Index keys on purpose: the list is a fixed 3 bands that are never
            inserted, removed or reordered, and `percentage` — the only other
            candidate — is user-editable and so collides mid-edit. */}
        {bands.map((band, index) => (
          <Tooltip
            key={index}
            label={band.active ? "On" : "Off"}
            openDelay={300}
          >
            <Box
              px={2}
              py={1}
              minW="52px"
              textAlign="center"
              fontSize="sm"
              borderWidth="1px"
              borderRadius="md"
              borderStyle={band.active ? "solid" : "dashed"}
              borderColor={band.active ? "blue.300" : "gray.200"}
              bg={band.active ? "blue.50" : "gray.50"}
              color={band.active ? "blue.800" : "gray.400"}
              fontWeight={band.active ? "semibold" : "normal"}
              aria-label={`${band.percentage} percent, ${band.active ? "on" : "off"}`}
            >
              {band.percentage}%
            </Box>
          </Tooltip>
        ))}
        <Tooltip label="Edit thresholds" hasArrow openDelay={300}>
          <IconButton
            aria-label={`Edit thresholds for ${rowLabel}`}
            icon={<HamburgerIcon boxSize={5} />}
            size="sm"
            variant="ghost"
            color="gray.700"
            onClick={handleOpen}
          />
        </Tooltip>
      </HStack>

      <StandardModal
        isOpen={isOpen}
        onClose={onClose}
        size="sm"
        title={`Edit thresholds — ${rowLabel}`}
        modalProps={{ initialFocusRef: firstInputRef }}
        footer={
          <HStack spacing={3}>
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button
              colorScheme="blue"
              onClick={handleApply}
              isDisabled={!validation.bands}
            >
              Apply
            </Button>
          </HStack>
        }
      >
        <VStack align="stretch" spacing={3}>
          <Text fontSize="sm" color="gray.600">
            Check the thresholds that should fire and set each percentage.{" "}
            {MIN_THRESHOLD_PERCENT}-{MAX_THRESHOLD_PERCENT}%, no duplicates.
          </Text>

          {/* Index keys for the same reason as the boxes above — and here a
              percentage key would actively break things: two fields briefly
              share a number while retyping, and React would drop one. */}
          {editBands.map((band, index) => {
            const error = validation.bandErrors[index] ?? "";
            return (
              <Box key={index}>
                <HStack spacing={3}>
                  <Checkbox
                    isChecked={band.active}
                    onChange={(e) =>
                      updateBand(index, { active: e.target.checked })
                    }
                    aria-label={`Enable threshold ${index + 1}`}
                  />
                  <Input
                    ref={index === 0 ? firstInputRef : undefined}
                    value={band.percentage}
                    onChange={(e) =>
                      updateBand(index, { percentage: e.target.value })
                    }
                    aria-label={`Threshold ${index + 1} percent`}
                    isInvalid={Boolean(error)}
                    inputMode="numeric"
                    // 3 chars, not 2: typing 100 and being told "1-99 only"
                    // explains the rule, where silently refusing the
                    // keystroke just looks broken.
                    maxLength={3}
                    size="sm"
                    w="80px"
                    textAlign="right"
                  />
                  <Text fontSize="sm" color="gray.600">
                    %
                  </Text>
                  {error ? (
                    <Text fontSize="xs" color="red.500">
                      {error}
                    </Text>
                  ) : null}
                </HStack>
              </Box>
            );
          })}

          {validation.rowError ? (
            <Text fontSize="xs" color="red.500">
              {validation.rowError}
            </Text>
          ) : null}

          <Text fontSize="xs" color="gray.500">
            Applies to this row only. Nothing is saved until you Submit.
          </Text>
        </VStack>
      </StandardModal>
    </>
  );
};

export default ThresholdBandsCell;
