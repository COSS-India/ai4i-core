// Content layout wrapper component for page content

import React from 'react';
import { Box, useColorModeValue, useMediaQuery } from '@chakra-ui/react';

interface ContentLayoutProps {
  children: React.ReactNode;
}

const ContentLayout: React.FC<ContentLayoutProps> = ({ children }) => {
  const bgColor = useColorModeValue('light.100', 'dark.100');
  const [isMobile] = useMediaQuery('(max-width: 1080px)');

  return (
    <Box 
      pt={isMobile ? "3.5rem" : "calc(3.5rem + 0.5rem)"}
      pl={isMobile ? 4 : "calc(4.5rem + 1rem)"}
      pr={4}
      pb={4}
      flex="1"
      minH={0}
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
        overflow="auto"
        w="100%"
        maxW="1400px"
        mx="auto"
      >
        {children}
      </Box>
    </Box>
  );
};

export default ContentLayout;