// Playback preview for recorded/uploaded audio input (CSP-safe blob URL)

import React, { useEffect, useRef, useState } from 'react';
import { Box, Text } from '@chakra-ui/react';
import { base64ToAudioObjectUrl } from '../../utils/helpers';

/** Normalize base64 or data URL to [base64, format] for playback */
function normalizeAudioInput(value: string): { base64: string; format: string } {
  if (!value || !value.trim()) return { base64: '', format: 'wav' };
  const trimmed = value.trim();
  if (trimmed.startsWith('data:')) {
    const match = trimmed.match(/^data:audio\/(\w+);base64,(.+)$/);
    if (match) {
      const format = match[1].toLowerCase() === 'mpeg' ? 'mp3' : match[1];
      return { base64: match[2], format };
    }
    const fallback = trimmed.split(',')[1];
    return { base64: fallback || trimmed, format: 'wav' };
  }
  return { base64: trimmed, format: 'wav' };
}

export interface AudioInputPreviewProps {
  /** Base64-encoded audio or data URL (from recording/upload) */
  audioBase64OrDataUrl: string | null;
  /** Optional format when known (e.g. "mp3" for uploads) */
  format?: string;
  /** Label above the player */
  label?: string;
}

/**
 * Renders an audio player for the current input (recorded or uploaded) so users can review/play it.
 * Uses a blob URL so playback works with CSP (media-src blob:).
 */
const AudioInputPreview: React.FC<AudioInputPreviewProps> = ({
  audioBase64OrDataUrl,
  format: formatProp,
  label = 'Review your audio',
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
      <Text fontSize="sm" fontWeight="semibold" color="gray.700" mb={2}>
        {label}
      </Text>
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
