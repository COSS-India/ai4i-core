// Playback preview for recorded/uploaded audio input (CSP-safe blob URL)

import React, { useEffect, useRef, useState } from 'react';
import { Box, HStack, IconButton, Text, Tooltip } from '@chakra-ui/react';
import { DeleteIcon } from '@chakra-ui/icons';
import { base64ToAudioObjectUrl } from '../../utils/helpers';

/** Normalize base64 or data URL to [base64, format] for playback */
function normalizeAudioInput(value: string): { base64: string; format: string } {
  if (!value || !value.trim()) return { base64: '', format: 'wav' };
  const trimmed = value.trim();
  if (trimmed.startsWith('data:')) {
    // Safely captures MIME types with parameters (e.g., audio/webm;codecs=opus)
    const match = trimmed.match(/^data:(audio\/[^;]+)(?:;[^,]*)?,(.*)$/);
    if (match) {
      return { base64: match[2], format: match[1] };
    }
    const fallback = trimmed.split(',')[1];
    return { base64: fallback || trimmed, format: 'audio/wav' };
  }
  return { base64: trimmed, format: 'audio/wav' };
}

export interface AudioInputPreviewProps {
  /** Base64-encoded audio or data URL (from recording/upload) */
  audioBase64OrDataUrl: string | null;
  /** Optional format when known (e.g. "mp3" for uploads) */
  format?: string;
  /** Label above the player */
  label?: string;
  /** Optional clear/delete action for the current input */
  onClear?: () => void;
  clearLabel?: string;
}

/**
 * Renders an audio player for the current input (recorded or uploaded) so users can review/play it.
 * Uses a blob URL so playback works with CSP (media-src blob:).
 */
const AudioInputPreview: React.FC<AudioInputPreviewProps> = ({
  audioBase64OrDataUrl,
  format: formatProp,
  label = 'Review your audio',
  onClear,
  clearLabel = 'Remove audio',
}) => {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const objectUrlRef = useRef<string | null>(null);

  useEffect(() => {
    if (!audioBase64OrDataUrl?.trim()) {
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
      setBlobUrl(null);
      return;
    }
    try {
      const { base64, format } = normalizeAudioInput(audioBase64OrDataUrl);
      if (!base64) {
        setBlobUrl(null);
        return;
      }
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
      const effectiveFormat = formatProp || format;
      const url = base64ToAudioObjectUrl(base64, effectiveFormat);
      objectUrlRef.current = url;
      setBlobUrl(url);
    } catch (e) {
      console.error('AudioInputPreview: failed to create blob URL', e);
      setBlobUrl(null);
    }
    return () => {
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
    };
  }, [audioBase64OrDataUrl, formatProp]);

  if (!audioBase64OrDataUrl || !blobUrl) return null;

  return (
    <Box mt={3} p={3} bg="gray.50" borderRadius="md" borderWidth="1px" borderColor="gray.200">
      <HStack justify="space-between" align="flex-start" mb={2}>
        <Text fontSize="sm" fontWeight="semibold" color="gray.700">
          {label}
        </Text>
        {onClear && (
          <Tooltip label={clearLabel} placement="top" hasArrow>
            <IconButton
              aria-label={clearLabel}
              icon={<DeleteIcon />}
              size="sm"
              variant="ghost"
              colorScheme="red"
              _hover={{ bg: "red.50" }}
              onClick={onClear}
            />
          </Tooltip>
        )}
      </HStack>
      <audio
        controls
        src={blobUrl ?? undefined}
        style={{ width: '100%', maxWidth: '400px' }}
        preload="metadata"
      >
        Your browser does not support the audio element.
      </audio>
    </Box>
  );
};

export default AudioInputPreview;
