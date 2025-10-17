// Main Next.js app component with providers and global layout

import React, { useState } from 'react';
import { AppProps } from 'next/app';
import { ChakraProvider } from '@chakra-ui/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { useRouter } from 'next/router';
import Script from 'next/script';
import customTheme from '../theme';
import Layout from '../components/common/Layout';
import '../styles/globals.css';

// Define routes that need the full layout
const layoutRoutes = ['/', '/asr', '/tts', '/nmt'];

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

  // Check if current route needs layout
  const needsLayout = layoutRoutes.includes(router.pathname);

  return (
    <ChakraProvider theme={customTheme}>
      <QueryClientProvider client={queryClient}>
        {/* Recorder.js Script */}
        <Script
          src="/recorder.js"
          strategy="beforeInteractive"
        />
        
        {/* Conditional Layout Rendering */}
        {needsLayout ? (
          <Layout>
            <Component {...pageProps} />
          </Layout>
        ) : (
          <Component {...pageProps} />
        )}
        
        {/* React Query DevTools */}
        <ReactQueryDevtools initialIsOpen={false} />
      </QueryClientProvider>
    </ChakraProvider>
  );
}