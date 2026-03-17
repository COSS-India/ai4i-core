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
      px={6}
      pb={4}
      flex="1"
      minH={0}
      minW={0}
      display="flex"
      flexDirection="column"
      w="100%"
    >
      <Box
        py={4}
        px={4}
        bg={bgColor}
        borderRadius="md"
        flex="1"
        minH={0}
        minW={0}
        overflow="auto"
        w="100%"
        maxW="1400px"
        mx="auto"
        sx={{ maxWidth: '100%' }}
      >
        {children}
      </Box>
    </Box>
  );
};

export default ContentLayout;