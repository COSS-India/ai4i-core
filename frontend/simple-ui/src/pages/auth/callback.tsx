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
        // Get tokens from URL query parameters
        const { access_token, refresh_token, token_type, error: oauthError } = router.query;

        // Check for OAuth errors
        if (oauthError) {
          setError(`OAuth error: ${oauthError}`);
          setIsProcessing(false);
          setTimeout(() => {
            router.push('/');
          }, 3000);
          return;
        }

        // Check if we have the required tokens
        if (!access_token || !refresh_token) {
          setError('Missing authentication tokens. Please try again.');
          setIsProcessing(false);
          setTimeout(() => {
            router.push('/');
          }, 3000);
          return;
        }

        // Store tokens
        authService.setAccessToken(access_token as string);
        authService.setRefreshToken(refresh_token as string);

        // Fetch user data to verify token and get user info
        try {
          const user = await authService.getCurrentUser();
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



