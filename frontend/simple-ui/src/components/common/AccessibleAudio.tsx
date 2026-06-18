// Accessible audio element with a captions track for SonarQube / WCAG compliance

import React, { useEffect, useMemo } from 'react';
import { createCaptionTrackBlobUrl } from '../../utils/captionTrack';

export interface AccessibleAudioProps
  extends React.AudioHTMLAttributes<HTMLAudioElement> {
  /** Plain-text transcript or caption content shown in the track. */
  captionText?: string;
  /** Duration in seconds used for caption timing (defaults to 1 hour). */
  captionDurationSeconds?: number;
  /** BCP-47 language code for the captions track. */
  captionLang?: string;
  /** Human-readable label for the captions track menu. */
  captionLabel?: string;
  /** Message used when captionText is not provided. */
  noCaptionsFallback?: string;
}

const AccessibleAudio = React.forwardRef<HTMLAudioElement, AccessibleAudioProps>(
  function AccessibleAudio(
    {
      captionText,
      captionDurationSeconds,
      captionLang = 'en',
      captionLabel,
      noCaptionsFallback = 'No captions available for this audio.',
      children,
      ...audioProps
    },
    ref
  ) {
    const trackUrl = useMemo(() => {
      const text = captionText?.trim() || noCaptionsFallback;
      return createCaptionTrackBlobUrl(text, captionDurationSeconds);
    }, [captionText, captionDurationSeconds, noCaptionsFallback]);

    useEffect(() => {
      return () => {
        URL.revokeObjectURL(trackUrl);
      };
    }, [trackUrl]);

    const label =
      captionLabel ??
      (captionLang === 'en' ? 'English captions' : `${captionLang} captions`);

    return (
      <audio ref={ref} {...audioProps}>
        <track
          kind="captions"
          src={trackUrl}
          srcLang={captionLang}
          label={label}
          default
        />
        {children}
      </audio>
    );
  }
);

export default AccessibleAudio;
