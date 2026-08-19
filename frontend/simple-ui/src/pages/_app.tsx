// Main Next.js app component with providers and global layout

import React, { useState } from 'react';
import { installGlobalErrorHandling } from '../utils/errorHandler';
import App, { AppContext, AppProps } from 'next/app';
import Head from 'next/head';
import { ChakraProvider } from '@chakra-ui/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { useRouter } from 'next/router';
import customTheme from '../theme';
import Layout from '../components/common/Layout';
import AppErrorBoundary from '../components/common/AppErrorBoundary';
import { GlobalToastRegistrar } from '../utils/toast';
import AuthGuard from '../components/auth/AuthGuard';
import {
  applyRuntimeConfig,
  DEFAULT_PLATFORM_NAME,
  getServerRuntimeConfig,
  type RuntimeConfig,
} from '../config/runtimeConfig';
import { syncApiClientBaseUrl } from '../services/api';
import '../styles/globals.css';
import '../styles/metering.css';

if (typeof window !== 'undefined') {
  installGlobalErrorHandling();
}

type AppOwnProps = { runtimeConfig: RuntimeConfig };

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
  '/institution-management',
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
  // Alerts Management removed from UI — uncomment to restore
  // '/alerts-management',
  // PII Guardrail removed from UI — uncomment to restore
  // '/pii-management',
  '/tier-management',
  '/policy-management',
];

export default function MyApp({
  Component,
  pageProps,
  runtimeConfig,
}: AppProps & Partial<AppOwnProps>) {
  // Apply before children render so hooks/services see ConfigMap values.
  applyRuntimeConfig(
    runtimeConfig ??
      (typeof window !== "undefined" ? window.__RUNTIME_CONFIG__ : undefined) ?? {
        apiUrl: "",
        telemetryServiceUrl: "",
        enabledTaskTypes: "",
        platformName: DEFAULT_PLATFORM_NAME,
        adopterLogoUrl: "",
      },
  );
  syncApiClientBaseUrl();

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
  const needsLayout = layoutRoutes.includes(router.pathname) && router.pathname !== '/auth';

  return (
    <ChakraProvider theme={customTheme}>
      <GlobalToastRegistrar />
      <AppErrorBoundary>
        <Head>
          <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=5, viewport-fit=cover" />
        </Head>
        <QueryClientProvider client={queryClient}>
          <AuthGuard>
            {needsLayout ? (
              <Layout>
                <Component {...pageProps} />
              </Layout>
            ) : (
              <Component {...pageProps} />
            )}
          </AuthGuard>
          <ReactQueryDevtools initialIsOpen={false} />
        </QueryClientProvider>
      </AppErrorBoundary>
    </ChakraProvider>
  );
}

MyApp.getInitialProps = async (appContext: AppContext) => {
  const appProps = await App.getInitialProps(appContext);

  let runtimeConfig: RuntimeConfig;
  if (typeof window === 'undefined') {
    runtimeConfig = getServerRuntimeConfig();
  } else if (window.__RUNTIME_CONFIG__) {
    runtimeConfig = window.__RUNTIME_CONFIG__;
  } else {
    const res = await fetch(`${window.location.origin}/api/config`);
    runtimeConfig = (await res.json()) as RuntimeConfig;
  }

  return { ...appProps, runtimeConfig };
};
