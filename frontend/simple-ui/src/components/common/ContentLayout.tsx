// Content layout wrapper component for page content

import React from 'react';
import { Box, useColorModeValue } from '@chakra-ui/react';

interface ContentLayoutProps {
  children: React.ReactNode;
}

const ContentLayout: React.FC<ContentLayoutProps> = ({ children }) => {
  const bgColor = useColorModeValue('white', 'dark.100');

  return (
    <Box
      px={{ base: 3, md: 5 }}
      pb={5}
      pt={3}
      flex="1"
      minH={0}
      minW={0}
      display="flex"
      flexDirection="column"
      w="100%"
    >
      <Box
        py={5}
        px={{ base: 4, md: 6 }}
        bg={bgColor}
        borderRadius="lg"
        border="1px solid"
        borderColor="ink.200"
        boxShadow="xs"
        flex="1"
        minH={0}
        minW={0}
        overflow="auto"
        w="100%"
      >
        {children}
      </Box>
    </Box>
  );
};

export default ContentLayout;
