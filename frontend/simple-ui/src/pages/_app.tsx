// Main Next.js app component with providers and global layout

import React, { useState } from 'react';
import { AppProps } from 'next/app';
import Head from 'next/head';
import { ChakraProvider } from '@chakra-ui/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { useRouter } from 'next/router';
import customTheme from '../theme';
// Force feature-flag module to load before Layout/Sidebar to avoid circular dependency (useFeatureFlagsBulk undefined)
import '../hooks/useFeatureFlag';
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
  '/traces',
  '/alerts-management',
  '/pii-management',
  // Admin / usage (also matched by /admin/* and /dashboard/* below)
  '/admin/quota-configs',
  '/admin/rate-limit-configs',
  '/admin/policies',
  '/dashboard/usage',
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

  // Prefer router.pathname; fallback to window during early client render so we don't skip Layout
  const path =
    router.pathname ||
    (typeof window !== 'undefined' ? window.location.pathname : '') ||
    '';
  const isAuthRoute = path === '/auth' || path.startsWith('/auth/');
  const needsLayout =
    (layoutRoutes.includes(path) ||
      path === '/admin' ||
      path.startsWith('/admin/') ||
      path === '/dashboard' ||
      path.startsWith('/dashboard/')) &&
    !isAuthRoute;

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