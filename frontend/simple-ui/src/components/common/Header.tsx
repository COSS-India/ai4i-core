// Header/navbar component for top navigation with authentication and API key management

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/router';
import {
  Box,
  HStack,
  Heading,
  Badge,
  Menu,
  MenuButton,
  MenuList,
  MenuItem,
  MenuDivider,
  IconButton,
  Image,
  useColorModeValue,
  Button
} from '@chakra-ui/react';
import { HamburgerIcon, ArrowBackIcon, ViewIcon, ViewOffIcon } from '@chakra-ui/icons';
import { useApiKey } from '../../hooks/useApiKey';
import ApiKeyModal from './ApiKeyModal';
import ApiKeyViewerModal from './ApiKeyViewerModal';
import { useAuth } from '../../hooks/useAuth';
import UserMenu from '../auth/UserMenu';
import AuthModal from '../auth/AuthModal';

const Header: React.FC = () => {
  const router = useRouter();
  const { apiKey, isAuthenticated: hasApiKey, clearApiKey } = useApiKey();
  const { isAuthenticated: isUserAuthenticated, user, isLoading: isAuthLoading, logout } = useAuth();

  const [isApiKeyModalOpen, setIsApiKeyModalOpen] = useState(false);
  const [isApiKeyViewerOpen, setIsApiKeyViewerOpen] = useState(false);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [title, setTitle] = useState('Dashboard');
  const [isApiKeyVisible, setIsApiKeyVisible] = useState(false);

  // Determine if we should show user menu or sign in button
  const showUserMenu = !isAuthLoading && isUserAuthenticated && user && user.username;

  // Update title based on route
  useEffect(() => {
    const pathname = router.pathname;
    switch (pathname) {
      case '/asr':
        setTitle('ASR – Automatic Speech Recognition');
        break;
      case '/tts':
        setTitle('TTS – Text-to-Speech');
        break;
      case '/nmt':
        setTitle('Text Translation');
        break;
      case '/llm':
        setTitle('Large Language Model - GPT OSS 20B');
        break;
      case '/pipeline':
        setTitle('Speech-to-Speech Pipeline');
        break;
      case '/pipeline-builder':
        setTitle('Pipeline Builder');
        break;
      case '/':
        setTitle('AI4Inclusion Console');
        break;
      default:
        setTitle('AI4Inclusion Console');
    }
  }, [router.pathname]);

  const handleManageApiKey = () => setIsApiKeyModalOpen(true);

  const handleClearApiKey = () => clearApiKey();

  const handleDocumentation = () => {
    console.log('Navigate to documentation');
  };

  const getApiKeyDisplay = () => {
    if (hasApiKey && apiKey) {
      const last4Chars = apiKey.slice(-4);
      return `API Key: ****${last4Chars}`;
    }
    return 'No API Key';
  };

  const getApiKeyColor = () => (hasApiKey ? 'green' : 'red');

  const bgColor = useColorModeValue('white', 'gray.800');
  const borderColor = useColorModeValue('gray.200', 'gray.700');
  const showBackButton = router.pathname !== '/';

  const handleBack = () => {
    if (router.pathname === '/pipeline-builder') {
      router.push('/');
    } else {
      router.back();
    }
  };

  const handleAuthClick = () => {
    console.log('Header: Sign In button clicked, opening AuthModal');
    setIsAuthModalOpen(true);
  };

  // Debug: Log API key state and modal state
  useEffect(() => {
    console.log('Header: API Key state:', { apiKey: apiKey ? '***' + apiKey.slice(-4) : null, hasApiKey });
    console.log('Header: AuthModal state:', { isAuthModalOpen });
  }, [apiKey, hasApiKey, isAuthModalOpen]);

  return (
    <>
      <Box
        h="6.5rem"
        bg={bgColor}
        px="2rem"
        boxShadow="sm"
        position="sticky"
        top={0}
        zIndex={10}
        borderBottom="1px"
        borderColor={borderColor}
      >
        <HStack justify="space-between" h="full">
          {/* Left side - Back button, Logo and Page title */}
          <HStack spacing={4}>
            {showBackButton && (
              <IconButton
                aria-label="Go back"
                icon={<ArrowBackIcon />}
                variant="ghost"
                size="md"
                onClick={handleBack}
                colorScheme="gray"
                _hover={{ bg: 'gray.100' }}
              />
            )}
            {router.pathname !== '/' && (
              <Box
                cursor="pointer"
                onClick={() => router.push('/')}
                _hover={{ opacity: 0.8 }}
                transition="opacity 0.2s"
              >
                <Image
                  src="/AI4Inclusion_Logo.svg"
                  alt="AI4Inclusion Logo"
                  h="50px"
                  w="auto"
                  objectFit="contain"
                />
              </Box>
            )}
            <Heading size="lg" color="gray.800">
              {title}
            </Heading>
          </HStack>

          {/* Right side - Menu and Auth */}
          <HStack spacing={4}>
            {/* Authentication: On home page, show only username after sign-in; elsewhere keep existing behavior */}
            {router.pathname === '/' ? (
              showUserMenu ? (
                <Badge colorScheme="gray" fontSize="sm" px={3} py={1} borderRadius="md">
                  {user.username}
                </Badge>
              ) : (
                <Button
                  colorScheme="blue"
                  variant="outline"
                  size="sm"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    console.log('Header: Sign In button clicked');
                    handleAuthClick();
                  }}
                >
                  Sign In
                </Button>
              )
            ) : (
              showUserMenu ? (
                <UserMenu user={user} />
              ) : (
                <Button
                  colorScheme="blue"
                  variant="outline"
                  size="sm"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    console.log('Header: Sign In button clicked');
                    handleAuthClick();
                  }}
                >
                  Sign In
                </Button>
              )
            )}

            {/* Menu */}
            <Menu>
              <MenuButton
                as={IconButton}
                aria-label="Options"
                icon={<HamburgerIcon />}
                variant="ghost"
                size="sm"
              />
              <MenuList>
                {router.pathname === '/' ? (
                  <>
                    <MenuItem onClick={() => setIsApiKeyViewerOpen(true)}>API Key</MenuItem>
                    <MenuItem onClick={() => logout()}>Sign out</MenuItem>
                  </>
                ) : (
                  <>
                    <MenuItem onClick={handleManageApiKey}>Manage API Key</MenuItem>
                    <MenuItem onClick={handleClearApiKey} isDisabled={!hasApiKey}>Clear API Key</MenuItem>
                    <MenuDivider />
                    <MenuItem onClick={handleDocumentation}>Documentation</MenuItem>
                  </>
                )}
              </MenuList>
            </Menu>
          </HStack>
        </HStack>
      </Box>

      {/* API Key Modal (kept for non-home pages via menu) */}
      <ApiKeyModal
        isOpen={isApiKeyModalOpen}
        onClose={() => setIsApiKeyModalOpen(false)}
      />

      {/* API Key Viewer Modal (home page) */}
      <ApiKeyViewerModal
        isOpen={isApiKeyViewerOpen}
        onClose={() => setIsApiKeyViewerOpen(false)}
      />

      {/* Auth Modal */}
      <AuthModal
        isOpen={isAuthModalOpen}
        onClose={() => {
          console.log('Header: Closing AuthModal');
          setIsAuthModalOpen(false);
        }}
        initialMode="login"
      />
    </>
  );
};

export default Header;
