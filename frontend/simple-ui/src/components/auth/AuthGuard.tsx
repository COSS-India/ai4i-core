/**
 * Authentication guard component - protects routes and redirects to auth page if not authenticated
 */
import React, { useEffect } from 'react';
import { useRouter } from 'next/router';
import { Spinner, Center } from '@chakra-ui/react';
import { useAuth } from '../../hooks/useAuth';
import { canAccessUsageDashboard } from '../../utils/rbac';

interface AuthGuardProps {
  children: React.ReactNode;
}

// Routes that require authentication
// Note: /llm is excluded to allow anonymous "try-it" access (AI4IDS-2688)
const protectedRoutes = new Set([
  '/asr', '/tts', '/pipeline', '/pipeline-builder', '/model-management',
  '/services-management', '/tenant-management', '/api-key-management', '/profile',
  '/logs', '/usage-dashboard', '/traces',
  // AI4IDS-2604 / AI4IDS-2605: restore '/alerts-management', '/pii-management' when re-enabling UI
  '/policy-management',
]);

// Routes that require ADMIN role
// AI4IDS-2604: Alerts Management removed from UI — restore '/alerts-management' when re-enabling
const adminOnlyRoutes = new Set<string>([/* '/alerts-management' */]);

// Routes limited to Usage Dashboard eligible roles (Adopter Admin, Tenant Admin, platform ADMIN)
const usageDashboardRoutes = new Set(['/usage-dashboard']);

// Routes that allow anonymous access with limited functionality
// AI4IDS-2688: LLM try-it for anonymous users (replaces NMT as primary try-it surface)
const tryItRoutes = new Set(['/llm', '/nmt']);

const AuthGuard: React.FC<AuthGuardProps> = ({ children }) => {
  const router = useRouter();
  const { isAuthenticated, isLoading, user } = useAuth();

  // Check if current route requires authentication
  const isProtectedRoute = protectedRoutes.has(router.pathname);
  const isAdminOnlyRoute = adminOnlyRoutes.has(router.pathname);
  const isUsageDashboardRoute = usageDashboardRoutes.has(router.pathname);
  const isTryItRoute = tryItRoutes.has(router.pathname);

  // Check if user is ADMIN
  const isAdmin = user?.roles?.includes('ADMIN') || false;
  const canAccessUsage = canAccessUsageDashboard(user?.roles);

  // Redirect to auth page if accessing protected route without authentication
  // Allow access to try-it routes (like /nmt) for anonymous users
  useEffect(() => {
    if (!isLoading && isProtectedRoute && !isAuthenticated && !isTryItRoute) {
      console.log('AuthGuard: Protected route detected, user not authenticated, redirecting to /auth');
      router.push('/auth');
    }
  }, [isLoading, isProtectedRoute, isAuthenticated, isTryItRoute, router]);

  // Redirect non-ADMIN users away from admin-only routes
  useEffect(() => {
    if (!isLoading && isAdminOnlyRoute && (!isAuthenticated || !isAdmin)) {
      console.log('AuthGuard: Admin-only route detected, user is not ADMIN, redirecting to home');
      router.push('/');
    }
  }, [isLoading, isAdminOnlyRoute, isAuthenticated, isAdmin, router]);

  // Redirect users without Usage Dashboard access
  useEffect(() => {
    if (!isLoading && isUsageDashboardRoute && isAuthenticated && !canAccessUsage) {
      console.log('AuthGuard: Usage dashboard route denied for current roles, redirecting to home');
      router.push('/');
    }
  }, [isLoading, isUsageDashboardRoute, isAuthenticated, canAccessUsage, router]);

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

  // If admin-only route and user is not ADMIN, don't render children (will redirect)
  if (isAdminOnlyRoute && (!isAuthenticated || !isAdmin)) {
    return null; // Will redirect via useEffect
  }

  // If usage dashboard route and user lacks access, don't render children (will redirect)
  if (isUsageDashboardRoute && isAuthenticated && !canAccessUsage) {
    return null;
  }

  // Allow access if:
  // 1. User is authenticated, OR
  // 2. Route is not protected, OR
  // 3. Route is a try-it route (like /nmt for anonymous users)
  // 4. For admin-only routes, user must be ADMIN
  return <>{children}</>;
};

export default AuthGuard;
