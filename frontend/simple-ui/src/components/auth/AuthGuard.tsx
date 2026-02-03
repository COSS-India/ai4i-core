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
// Note: /nmt is excluded to allow anonymous "try-it" access
const protectedRoutes = ['/asr', '/tts', '/llm', '/pipeline', '/pipeline-builder', '/model-management', '/services-management', '/profile'];

// Routes that allow anonymous access with limited functionality
const tryItRoutes = ['/nmt'];

const AuthGuard: React.FC<AuthGuardProps> = ({ children }) => {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();

  // Check if current route requires authentication
  const isProtectedRoute = protectedRoutes.includes(router.pathname);
  const isTryItRoute = tryItRoutes.includes(router.pathname);

  // Redirect to auth page if accessing protected route without authentication
  // Allow access to try-it routes (like /nmt) for anonymous users
  useEffect(() => {
    if (!isLoading && isProtectedRoute && !isAuthenticated && !isTryItRoute) {
      console.log('AuthGuard: Protected route detected, user not authenticated, redirecting to /auth');
      router.push('/auth');
    }
  }, [isLoading, isProtectedRoute, isAuthenticated, isTryItRoute, router]);

  // Show loading spinner while checking auth
  if (isLoading) {
    return (
      <Center h="100vh">
        <Spinner size="xl" color="orange.500" />
      </Center>
    );
  }

  // If protected route and not authenticated, don't render children (will redirect)
  // Allow try-it routes for anonymous users
  if (isProtectedRoute && !isAuthenticated && !isTryItRoute) {
    return null; // Will redirect via useEffect
  }

  // Allow access if:
  // 1. User is authenticated, OR
  // 2. Route is not protected, OR
  // 3. Route is a try-it route (like /nmt for anonymous users)
  return <>{children}</>;
};

export default AuthGuard;

