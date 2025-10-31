// Custom Next.js document for HTML structure and meta tags

import { Html, Head, Main, NextScript } from 'next/document';

export default function Document() {
  return (
    <Html lang="en">
      <Head>
        {/* Meta Tags */}
        <meta charSet="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta
          name="description"
          content="Simple UI for testing ASR, TTS, and NMT microservices"
        />
        <meta name="keywords" content="ASR, TTS, NMT, AI, speech recognition, text-to-speech, translation" />
        <meta name="author" content="AI4Bharat" />
        
        {/* Favicon */}
        <link rel="icon" href="/favicon.ico" />
        
        {/* Google Fonts */}
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
        
        {/* Theme Color */}
        <meta name="theme-color" content="#ff8c00" />
        
        {/* Open Graph Meta Tags */}
        <meta property="og:title" content="Simple UI - AI Accessibility Studio" />
        <meta property="og:description" content="Test ASR, TTS, and NMT microservices with a modern web interface" />
        <meta property="og:type" content="website" />
        <meta property="og:image" content="/og-image.png" />
        
        {/* Twitter Card Meta Tags */}
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content="Simple UI - AI Accessibility Studio" />
        <meta name="twitter:description" content="Test ASR, TTS, and NMT microservices with a modern web interface" />
        <meta name="twitter:image" content="/twitter-image.png" />
      </Head>
      <body>
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}