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
  IconButton,
  useColorModeValue,
  Button
} from '@chakra-ui/react';
import { HamburgerIcon, ArrowBackIcon } from '@chakra-ui/icons';
import ApiKeyViewerModal from './ApiKeyViewerModal';
import { useAuth } from '../../hooks/useAuth';
import AuthModal from '../auth/AuthModal';

const Header: React.FC = () => {
  const router = useRouter();
  const { isAuthenticated: isUserAuthenticated, user, isLoading: isAuthLoading, logout } = useAuth();

  const [isApiKeyViewerOpen, setIsApiKeyViewerOpen] = useState(false);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [title, setTitle] = useState('Dashboard');

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

  // Debug: Log AuthModal state
  useEffect(() => {
    console.log('Header: AuthModal state:', { isAuthModalOpen });
  }, [isAuthModalOpen]);

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
            <Heading size="lg" color="gray.800">
              {title}
            </Heading>
          </HStack>

          {/* Right side - Menu and Auth */}
          <HStack spacing={4}>
            {/* Authentication: Show username badge or Sign In button */}
            {showUserMenu ? (
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
                <MenuItem onClick={() => setIsApiKeyViewerOpen(true)}>API Key</MenuItem>
                <MenuItem onClick={() => logout()}>Sign out</MenuItem>
              </MenuList>
            </Menu>
          </HStack>
        </HStack>
      </Box>

      {/* API Key Viewer Modal */}
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
