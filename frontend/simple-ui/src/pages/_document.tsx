// Custom Next.js document for HTML structure and meta tags

import { Html, Head, Main, NextScript } from 'next/document';
import {
  DEFAULT_PLATFORM_NAME,
  getServerRuntimeConfig,
} from '../config/runtimeConfig';

export default function Document() {
  const platformName =
    getServerRuntimeConfig().platformName || DEFAULT_PLATFORM_NAME;

  return (
    <Html lang="en">
      <Head>
        {/* Meta Tags */}
        <meta charSet="UTF-8" />
        <meta
          name="description"
          content={`${platformName} console for Language AI services`}
        />
        <meta name="keywords" content="ASR, TTS, NMT, LLM, AI, speech recognition, text-to-speech, translation" />
        <meta name="author" content="COSS" />

        {/* Favicon */}
        <link rel="icon" href="/favicon.ico" />

        {/* Google Fonts */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap"
          rel="stylesheet"
        />

        {/* Theme Color */}
        <meta name="theme-color" content="#0F172A" />

        {/* Open Graph Meta Tags */}
        <meta property="og:title" content={platformName} />
        <meta property="og:description" content={platformName} />
        <meta property="og:type" content="website" />
        <meta property="og:image" content="/og-image.png" />

        {/* Twitter Card Meta Tags */}
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content={platformName} />
        <meta name="twitter:description" content={platformName} />
        <meta name="twitter:image" content="/twitter-image.png" />
      </Head>
      <body>
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
