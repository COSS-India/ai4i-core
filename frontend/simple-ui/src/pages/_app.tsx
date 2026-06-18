// Main Next.js app component with providers and global layout

import React, { useEffect, useState } from 'react';
import { showErrorAlert } from '../utils/errorHandler';
import { AppProps } from 'next/app';
import Head from 'next/head';
import { ChakraProvider } from '@chakra-ui/react';
import { QueryClient, QueryClientProvider, QueryCache, MutationCache } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { useRouter } from 'next/router';
import customTheme from '../theme';
import Layout from '../components/common/Layout';
import AuthGuard from '../components/auth/AuthGuard';
import '../styles/globals.css';
import '../styles/metering.css';

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
  '/tenant-management',
  '/api-key-management',
  '/ocr',
  '/transliteration',
  '/language-detection',
  '/speaker-diarization',
  '/language-diarization',
  '/audio-language-detection',
  '/ner',
  '/logs',
  '/usage-dashboard',
  '/traces',
  '/alerts-management',
  '/pii-management',
  '/policy-management',
];

export default function App({ Component, pageProps }: AppProps) {
  const router = useRouter();
  const [queryClient] = useState(
    () =>
      new QueryClient({
        queryCache: new QueryCache({
          onError: (error, query) => {
            if (query.meta?.suppressErrorAlert) return;
            showErrorAlert(error);
          },
        }),
        mutationCache: new MutationCache({
          onError: (error, _variables, _context, mutation) => {
            if (mutation.meta?.suppressErrorAlert) return;
            if (mutation.options.onError) return;
            showErrorAlert(error);
          },
        }),
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
  const needsLayout = layoutRoutes.includes(router.pathname) && router.pathname !== '/auth';

  useEffect(() => {
    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      event.preventDefault();
      showErrorAlert(event.reason);
    };

    const handleWindowError = (event: ErrorEvent) => {
      event.preventDefault();
      showErrorAlert(event.error ?? event.message);
    };

    window.addEventListener('unhandledrejection', handleUnhandledRejection);
    window.addEventListener('error', handleWindowError);
    return () => {
      window.removeEventListener('unhandledrejection', handleUnhandledRejection);
      window.removeEventListener('error', handleWindowError);
    };
  }, []);

  return (
    <ChakraProvider theme={customTheme}>
      <Head>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=5, viewport-fit=cover" />
      </Head>
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
