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
  Button,
  useColorModeValue,
} from '@chakra-ui/react';
import { HamburgerIcon } from '@chakra-ui/icons';
import { useApiKey } from '../../hooks/useApiKey';
import { useAuth } from '../../hooks/useAuth';
import ApiKeyModal from './ApiKeyModal';
import AuthModal from '../auth/AuthModal';
import UserMenu from '../auth/UserMenu';

const Header: React.FC = () => {
  const router = useRouter();
  const { apiKey, isAuthenticated: hasApiKey, clearApiKey } = useApiKey();
  const { isAuthenticated: isUserAuthenticated, user } = useAuth();
  const [isApiKeyModalOpen, setIsApiKeyModalOpen] = useState(false);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [title, setTitle] = useState('AI4Inclusion Console');

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
      case '/pipeline':
        setTitle('Speech-to-Speech Pipeline');
        break;
      case '/':
        setTitle('AI4Inclusion Console');
        break;
      default:
        setTitle('AI4Inclusion Console');
    }
  }, [router.pathname]);

  const handleManageApiKey = () => {
    setIsApiKeyModalOpen(true);
  };

  const handleClearApiKey = () => {
    clearApiKey();
  };

  const handleDocumentation = () => {
    // Future: Navigate to documentation
    console.log('Navigate to documentation');
  };

  const getApiKeyDisplay = () => {
    if (hasApiKey && apiKey) {
      const last4Chars = apiKey.slice(-4);
      return `API Key: ****${last4Chars}`;
    }
    return 'No API Key';
  };

  const getApiKeyColor = () => {
    return hasApiKey ? 'green' : 'red';
  };

  const handleAuthClick = () => {
    setIsAuthModalOpen(true);
  };

  const bgColor = useColorModeValue('white', 'gray.800');
  const borderColor = useColorModeValue('gray.200', 'gray.700');

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
          {/* Left side - Page title */}
          <Heading size="lg" color="gray.800">
            {title}
          </Heading>

          {/* Right side - Authentication, API key status and menu */}
          <HStack spacing={4}>
            {/* Authentication */}
            {isUserAuthenticated && user ? (
              <UserMenu user={user} />
            ) : (
              <Button
                colorScheme="blue"
                variant="outline"
                size="sm"
                onClick={handleAuthClick}
              >
                Sign In
              </Button>
            )}

            {/* API Key Badge - Hidden for now */}
            {/* <Badge
              colorScheme={getApiKeyColor()}
              px={3}
              py={1}
              borderRadius="full"
              fontSize="sm"
            >
              {getApiKeyDisplay()}
            </Badge> */}

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
                <MenuItem onClick={handleManageApiKey}>
                  Manage API Key
                </MenuItem>
                <MenuItem onClick={handleClearApiKey} isDisabled={!hasApiKey}>
                  Clear API Key
                </MenuItem>
                <MenuDivider />
                <MenuItem onClick={handleDocumentation}>
                  Documentation
                </MenuItem>
              </MenuList>
            </Menu>
          </HStack>
        </HStack>
      </Box>

      {/* API Key Modal */}
      <ApiKeyModal
        isOpen={isApiKeyModalOpen}
        onClose={() => setIsApiKeyModalOpen(false)}
      />

      {/* Authentication Modal */}
      <AuthModal
        isOpen={isAuthModalOpen}
        onClose={() => setIsAuthModalOpen(false)}
      />
    </>
  );
};

export default Header;