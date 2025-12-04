// Content layout wrapper component for page content

import React from 'react';
import { Box, useColorModeValue } from '@chakra-ui/react';

interface ContentLayoutProps {
  children: React.ReactNode;
}

const ContentLayout: React.FC<ContentLayoutProps> = ({ children }) => {
  const bgColor = useColorModeValue('light.100', 'dark.100');

  return (
    <Box 
      pt="calc(3.5rem + 0.5rem)" 
      pl="calc(4.5rem + 1rem)"
      pr={4}
      pb={4}
      minH="calc(100vh - 3.5rem)"
    >
      <Box
        py={4}
        px={4}
        bg={bgColor}
        borderRadius="md"
        minH="calc(100vh - 3.5rem - 1rem)"
      >
        {children}
      </Box>
    </Box>
  );
};

export default ContentLayout;