// Content layout wrapper component for page content

import React from 'react';
import { Box, useColorModeValue } from '@chakra-ui/react';

interface ContentLayoutProps {
  children: React.ReactNode;
}

const ContentLayout: React.FC<ContentLayoutProps> = ({ children }) => {
  const bgColor = useColorModeValue('light.100', 'dark.100');

  return (
    <Box pt="1%" px="1%">
      <Box
        mt="1%"
        py="2%"
        px="2%"
        h="90%"
        bg={bgColor}
        borderRadius="md"
      >
        {children}
      </Box>
    </Box>
  );
};

export default ContentLayout;