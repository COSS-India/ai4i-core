/**
 * OAuth callback page - handles OAuth redirects and stores tokens
 */
import { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import { Box, Spinner, Text, VStack, Alert, AlertIcon, AlertTitle, AlertDescription } from '@chakra-ui/react';
import authService from '../../services/authService';

const OAuthCallback = () => {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(true);

  useEffect(() => {
    const handleOAuthCallback = async () => {
      try {
        // New flow: callback includes a one-time code.
        // Legacy flow: callback may still include access_token/refresh_token.
        const { code, access_token, refresh_token, error: oauthError } = router.query;

        // Check for OAuth errors
        if (oauthError) {
          setError(`OAuth error: ${oauthError}`);
          setIsProcessing(false);
          setTimeout(() => {
            router.push('/');
          }, 3000);
          return;
        }

        const rememberMe = typeof window !== 'undefined' && localStorage.getItem('remember_me') === 'true';
        let nextAccessToken = typeof access_token === 'string' ? access_token : '';
        let nextRefreshToken = typeof refresh_token === 'string' ? refresh_token : '';
        let nextUser: any = null;

        // Preferred path: exchange one-time code for tokens
        if (typeof code === 'string' && code.trim()) {
          const exchange = await authService.exchangeOAuthCode(code);
          nextAccessToken = exchange.access_token;
          nextRefreshToken = exchange.refresh_token;
          nextUser = exchange.user ?? null;
        }

        // Validate required tokens after exchange/legacy handling
        if (!nextAccessToken || !nextRefreshToken) {
          setError('Missing authentication tokens. Please try again.');
          setIsProcessing(false);
          setTimeout(() => {
            router.push('/');
          }, 3000);
          return;
        }

        // Store tokens
        authService.setAccessToken(nextAccessToken, rememberMe);
        authService.setRefreshToken(nextRefreshToken, rememberMe);

        // Fetch user data to verify token and get user info
        try {
          const user = nextUser || await authService.getCurrentUser();
          authService.setStoredUser(user);

          // Broadcast auth update event
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new Event('auth:updated'));
          }

          // Redirect to home page
          router.push('/');
        } catch (userError) {
          console.error('Failed to fetch user data:', userError);
          setError('Failed to verify authentication. Please try logging in again.');
          setIsProcessing(false);
          setTimeout(() => {
            router.push('/');
          }, 3000);
        }
      } catch (err) {
        console.error('OAuth callback error:', err);
        setError('An error occurred during authentication. Please try again.');
        setIsProcessing(false);
        setTimeout(() => {
          router.push('/');
        }, 3000);
      }
    };

    // Only process if router is ready
    if (router.isReady) {
      handleOAuthCallback();
    }
  }, [router.isReady, router.query, router]);

  return (
    <Box
      minH="100vh"
      display="flex"
      alignItems="center"
      justifyContent="center"
      bg="gray.50"
    >
      <VStack spacing={4} maxW="md" w="full" p={8}>
        {isProcessing ? (
          <>
            <Spinner size="xl" color="blue.500" thickness="4px" />
            <Text fontSize="lg" color="gray.700">
              Completing authentication...
            </Text>
          </>
        ) : error ? (
          <Alert status="error" borderRadius="md" width="full">
            <AlertIcon />
            <Box flex="1">
              <AlertTitle>Authentication Failed</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Box>
          </Alert>
        ) : (
          <>
            <Spinner size="xl" color="green.500" thickness="4px" />
            <Text fontSize="lg" color="gray.700">
              Authentication successful! Redirecting...
            </Text>
          </>
        )}
      </VStack>
    </Box>
  );
};

export default OAuthCallback;



