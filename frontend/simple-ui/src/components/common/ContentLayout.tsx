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
      pt={2} 
      pl="calc(4.5rem + 1rem)"
      pr={4}
      h="calc(100vh - 3.5rem)"
      overflow="hidden"
    >
      <Box
        h="full"
        py={4}
        px={4}
        bg={bgColor}
        borderRadius="md"
        overflow="auto"
      >
        {children}
      </Box>
    </Box>
  );
};

export default ContentLayout;