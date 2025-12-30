/**
 * Authentication guard component - protects routes and redirects to auth page if not authenticated
 */
import React, { useEffect } from 'react';
import { useRouter } from 'next/router';
import { Spinner, Center } from '@chakra-ui/react';
import { useAuth } from '../../hooks/useAuth';

interface AuthGuardProps {
  children: React.ReactNode;
}

// Routes that require authentication
const protectedRoutes = ['/asr', '/tts', '/nmt', '/llm', '/pipeline', '/pipeline-builder', '/model-management', '/profile'];

const AuthGuard: React.FC<AuthGuardProps> = ({ children }) => {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();

  // Check if current route requires authentication
  const isProtectedRoute = protectedRoutes.includes(router.pathname);

  // Redirect to auth page if accessing protected route without authentication
  useEffect(() => {
    if (!isLoading && isProtectedRoute && !isAuthenticated) {
      console.log('AuthGuard: Protected route detected, user not authenticated, redirecting to /auth');
      router.push('/auth');
    }
  }, [isLoading, isProtectedRoute, isAuthenticated, router]);

  // Show loading spinner while checking auth
  if (isLoading) {
    return (
      <Center h="100vh">
        <Spinner size="xl" color="orange.500" />
      </Center>
    );
  }

  // If protected route and not authenticated, don't render children (will redirect)
  if (isProtectedRoute && !isAuthenticated) {
    return null; // Will redirect via useEffect
  }

  // Allow access if authenticated or route is not protected
  return <>{children}</>;
};

export default AuthGuard;

