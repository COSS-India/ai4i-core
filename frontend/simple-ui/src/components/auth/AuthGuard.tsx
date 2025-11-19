  /**
 * Authentication guard component - protects routes and shows login modal if not authenticated
 */
import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import { Box, Spinner, Center } from '@chakra-ui/react';
import { useAuth } from '../../hooks/useAuth';
import AuthModal from './AuthModal';

interface AuthGuardProps {
  children: React.ReactNode;
}

// Routes that require authentication
const protectedRoutes = ['/asr', '/tts', '/nmt', '/pipeline', '/pipeline-builder'];

const AuthGuard: React.FC<AuthGuardProps> = ({ children }) => {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();
  const [showAuthModal, setShowAuthModal] = useState(false);

  useEffect(() => {
    const isProtectedRoute = protectedRoutes.includes(router.pathname);

    if (!isLoading) {
      if (isProtectedRoute && !isAuthenticated) {
        // Show auth modal for protected routes when not authenticated
        console.log('AuthGuard: Protected route detected, user not authenticated, showing modal');
        setShowAuthModal(true);
      } else if (isAuthenticated) {
        // User is authenticated - ensure modal is closed if it was open
        if (showAuthModal) {
          console.log('AuthGuard: User authenticated, closing modal immediately');
          setShowAuthModal(false);
        }
        // Allow access to protected route now that user is authenticated
      }
    }
  }, [isAuthenticated, isLoading, router.pathname, showAuthModal]);

  // Show loading spinner while checking auth
  if (isLoading) {
    return (
      <Center h="100vh">
        <Spinner size="xl" color="orange.500" />
      </Center>
    );
  }

  // Check if current route requires authentication
  const isProtectedRoute = protectedRoutes.includes(router.pathname);

  // If protected route and not authenticated, show modal but still render children (will be blocked)
  if (isProtectedRoute && !isAuthenticated) {
    return (
      <>
        <Box opacity={0.5} pointerEvents="none">
          {children}
        </Box>
        <AuthModal
          isOpen={showAuthModal}
          onClose={() => {
            setShowAuthModal(false);
            // Redirect to home if user closes modal without authenticating
            if (router.pathname !== '/') {
              router.push('/');
            }
          }}
          initialMode="login"
        />
      </>
    );
  }

  // Allow access if authenticated or route is not protected
  // Don't show any modal on non-protected routes (like home page)
  return <>{children}</>;
};

export default AuthGuard;

