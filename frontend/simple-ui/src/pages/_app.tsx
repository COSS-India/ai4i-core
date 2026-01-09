// Main Next.js app component with providers and global layout

import React, { useState } from 'react';
import { AppProps } from 'next/app';
import { ChakraProvider } from '@chakra-ui/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { useRouter } from 'next/router';
import customTheme from '../theme';
import Layout from '../components/common/Layout';
import AuthGuard from '../components/auth/AuthGuard';
import '../styles/globals.css';

// Define routes that need the full layout
const layoutRoutes = [
  '/', 
  '/asr', 
  '/tts', 
  '/nmt', 
  '/llm', 
  '/pipeline', 
  '/pipeline-builder', 
  '/profile', 
  '/model-management',
  '/services-management',
  '/ocr',
  '/transliteration',
  '/language-detection',
  '/speaker-diarization',
  '/language-diarization',
  '/audio-language-detection',
  '/ner',
  '/tracing',
];

export default function App({ Component, pageProps }: AppProps) {
  const router = useRouter();
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: false,
            retry: 1,
            staleTime: 5 * 60 * 1000, // 5 minutes
          },
          mutations: {
            retry: 0,
          },
        },
      })
  );

  // Check if current route needs layout (exclude auth page)
  // Handle dynamic routes like /tracing/[traceId]
  const isTracingRoute = router.pathname.startsWith('/tracing');
  const needsLayout = (layoutRoutes.includes(router.pathname) || isTracingRoute) && router.pathname !== '/auth';

  return (
    <ChakraProvider theme={customTheme}>
      <QueryClientProvider client={queryClient}>
        {/* Conditional Layout Rendering with Auth Guard */}
        <AuthGuard>
          {needsLayout ? (
            <Layout>
              <Component {...pageProps} />
            </Layout>
          ) : (
            <Component {...pageProps} />
          )}
        </AuthGuard>
        
        {/* React Query DevTools */}
        <ReactQueryDevtools initialIsOpen={false} />
      </QueryClientProvider>
    </ChakraProvider>
  );
}