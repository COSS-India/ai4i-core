// Collapsible sidebar component for navigation

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/router';
import {
  Box,
  VStack,
  Button,
  Text,
  Image,
  Divider,
  useColorModeValue,
  useMediaQuery,
} from '@chakra-ui/react';
import {
  IoHomeOutline,
  IoVolumeHighOutline,
  IoLanguageOutline,
  IoGitNetworkOutline,
  IoSparklesOutline,
} from 'react-icons/io5';
import { FaMicrophone } from 'react-icons/fa';
import { useAuth } from '../../hooks/useAuth';
import AuthModal from '../auth/AuthModal';

interface NavItem {
  id: string;
  label: string;
  path: string;
  icon: React.ComponentType;
  requiresAuth?: boolean;
}

const navItems: NavItem[] = [
  { id: 'home', label: 'Home', path: '/', icon: IoHomeOutline, requiresAuth: false },
  { id: 'asr', label: 'ASR', path: '/asr', icon: FaMicrophone, requiresAuth: true },
  { id: 'tts', label: 'TTS', path: '/tts', icon: IoVolumeHighOutline, requiresAuth: true },
  { id: 'nmt', label: 'NMT', path: '/nmt', icon: IoLanguageOutline, requiresAuth: true },
  { id: 'llm', label: 'LLM', path: '/llm', icon: IoSparklesOutline, requiresAuth: true },
  { id: 'pipeline', label: 'Pipeline', path: '/pipeline', icon: IoGitNetworkOutline, requiresAuth: true },
];


const Sidebar: React.FC = () => {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();
  const [isExpanded, setIsExpanded] = useState(false);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [pendingNavigation, setPendingNavigation] = useState<string | null>(null);
  const [isMobile] = useMediaQuery('(max-width: 1080px)');

  // Navigate when authenticated and there's a pending navigation
  useEffect(() => {
    console.log('Sidebar useEffect:', { isAuthenticated, isLoading, pendingNavigation, showAuthModal });
    if (!isLoading && isAuthenticated && pendingNavigation) {
      console.log('✅ Sidebar: Authentication detected, navigating to pending route:', pendingNavigation);
      const navPath = pendingNavigation;
      setPendingNavigation(null); // Clear before navigation
      setShowAuthModal(false); // Close modal
      // Navigate immediately - no delay needed
      router.push(navPath);
    }
  }, [isAuthenticated, isLoading, pendingNavigation, router, showAuthModal]);

  // Also handle case where user becomes authenticated but there's no pending navigation
  useEffect(() => {
    if (!isLoading && isAuthenticated && showAuthModal) {
      console.log('Sidebar: User authenticated, closing modal');
      setShowAuthModal(false);
    }
  }, [isAuthenticated, isLoading, showAuthModal]);

  const bgColor = useColorModeValue('light.100', 'dark.100');
  const borderColor = useColorModeValue('gray.200', 'gray.700');
  const hoverBgColor = useColorModeValue('orange.50', 'orange.900');

  // Hide sidebar on mobile
  if (isMobile) {
    return null;
  }

  return (
    <Box
      position="fixed"
      left={0}
      top={0}
      h="100vh"
      w={isExpanded ? '300px' : '85px'}
      bg={bgColor}
      boxShadow="md"
      zIndex={50}
      transition="width 0.2s ease"
      onMouseEnter={() => setIsExpanded(true)}
      onMouseLeave={() => setIsExpanded(false)}
      borderRight="1px"
      borderColor={borderColor}
    >
      <VStack spacing={4} p={4} h="full">
        {/* Logo Section */}
        <VStack spacing={2} w="full">
          <Box
            cursor="pointer"
            onClick={() => router.push('/')}
            _hover={{ opacity: 0.8 }}
            transition="opacity 0.2s"
          >
            <Image
              src="/AI4Inclusion_Logo.svg"
              alt="AI4Inclusion Logo"
              boxSize="40px"
              objectFit="contain"
              fallback={
                <Box
                  boxSize="40px"
                  bg="orange.500"
                  borderRadius="md"
                  display="flex"
                  alignItems="center"
                  justifyContent="center"
                  color="white"
                  fontWeight="bold"
                  fontSize="lg"
                >
                  AI
                </Box>
              }
            />
          </Box>
        </VStack>

        <Divider />

        {/* Navigation Items */}
        <VStack spacing={2} w="full" align="stretch">
          {navItems.map((item) => {
            const isActive = router.pathname === item.path;
            const Icon = item.icon;
            const requiresAuth = item.requiresAuth ?? false;

                   const handleClick = async (e: React.MouseEvent) => {
                     e.preventDefault();
                     
                     // Wait for auth to finish loading before checking
                     if (isLoading) {
                       console.log('Sidebar: Auth still loading, waiting...');
                       return;
                     }

                     if (item.path === '/') {
                       router.push('/');
                     } else if (requiresAuth && !isAuthenticated) {
                       console.log('Sidebar: User not authenticated, showing modal for:', item.path);
                       setPendingNavigation(item.path);
                       setShowAuthModal(true);
                     } else if (isAuthenticated) {
                       // User is authenticated - navigate directly
                       console.log('Sidebar: User authenticated, navigating to:', item.path);
                       // Clear any pending navigation since we're navigating now
                       setPendingNavigation(null);
                       setShowAuthModal(false);
                       // Small delay to ensure state updates have propagated
                       await new Promise(resolve => setTimeout(resolve, 50));
                       router.push(item.path);
                     } else {
                       console.log('Sidebar: Navigating to:', item.path);
                       router.push(item.path);
                     }
                   };

            return (
              <Button
                key={item.id}
                variant="ghost"
                size="sm"
                h="40px"
                w="full"
                justifyContent={isExpanded ? 'flex-start' : 'center'}
                leftIcon={isExpanded ? <Icon /> : undefined}
                bg={isActive ? 'orange.500' : 'transparent'}
                color={isActive ? 'white' : 'gray.700'}
                boxShadow={isActive ? 'md' : 'none'}
                onClick={handleClick}
                _hover={{
                  bg: isActive ? 'orange.600' : hoverBgColor,
                  transform: 'translateY(-1px)',
                }}
                transition="all 0.2s"
              >
                {isExpanded ? item.label : <Icon />}
              </Button>
            );
          })}
        </VStack>
      </VStack>

      {/* Auth Modal for protected routes */}
      <AuthModal
        isOpen={showAuthModal}
        onClose={() => {
          setShowAuthModal(false);
          setPendingNavigation(null);
        }}
        initialMode="login"
      />
    </Box>
  );
};

export default Sidebar;