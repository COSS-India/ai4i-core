// Collapsible sidebar component for navigation

import React, { useState } from 'react';
import { useRouter } from 'next/router';
import Link from 'next/link';
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
} from 'react-icons/io5';
import { FaMicrophone } from 'react-icons/fa';

interface NavItem {
  id: string;
  label: string;
  path: string;
  icon: React.ComponentType;
}

const navItems: NavItem[] = [
  { id: 'home', label: 'Home', path: '/', icon: IoHomeOutline },
  { id: 'asr', label: 'ASR', path: '/asr', icon: FaMicrophone },
  { id: 'tts', label: 'TTS', path: '/tts', icon: IoVolumeHighOutline },
  { id: 'nmt', label: 'NMT', path: '/nmt', icon: IoLanguageOutline },
];

const Sidebar: React.FC = () => {
  const router = useRouter();
  const [isExpanded, setIsExpanded] = useState(false);
  const [isMobile] = useMediaQuery('(max-width: 1080px)');

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
          <Image
            src="/logo.png"
            alt="AI4Bharat Logo"
            boxSize="40px"
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
          {isExpanded && (
            <Text fontSize="sm" fontWeight="bold" color="gray.700">
              Simple UI
            </Text>
          )}
        </VStack>

        <Divider />

        {/* Navigation Items */}
        <VStack spacing={2} w="full" align="stretch">
          {navItems.map((item) => {
            const isActive = router.pathname === item.path;
            const Icon = item.icon;

            return (
              <Link key={item.id} href={item.path} passHref>
                <Button
                  as="a"
                  variant="ghost"
                  size="sm"
                  h="40px"
                  w="full"
                  justifyContent={isExpanded ? 'flex-start' : 'center'}
                  leftIcon={<Icon />}
                  bg={isActive ? 'orange.500' : 'transparent'}
                  color={isActive ? 'white' : 'gray.700'}
                  boxShadow={isActive ? 'md' : 'none'}
                  _hover={{
                    bg: isActive ? 'orange.600' : hoverBgColor,
                    transform: 'translateY(-1px)',
                  }}
                  transition="all 0.2s"
                >
                  {isExpanded && item.label}
                </Button>
              </Link>
            );
          })}
        </VStack>
      </VStack>
    </Box>
  );
};

export default Sidebar;