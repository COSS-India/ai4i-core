// Content layout wrapper component for page content

import React from 'react';
import { Box, useColorModeValue } from '@chakra-ui/react';

interface ContentLayoutProps {
  children: React.ReactNode;
  /**
   * Lay the card out as a flex column so a child (e.g. an admin DataTable with
   * `fillHeight`) can shrink to the card's height and scroll internally,
   * instead of the card scrolling as well.
   */
  fillHeight?: boolean;
}

const ContentLayout: React.FC<ContentLayoutProps> = ({ children, fillHeight = false }) => {
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
        pt={5}
        // The card doesn't scroll under `fillHeight`, so its bottom padding is
        // always on screen; keep it tight so the table sits near the edge.
        pb={fillHeight ? 3 : 5}
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
        {...(fillHeight ? { display: 'flex', flexDirection: 'column' } : {})}
      >
        {children}
      </Box>
    </Box>
  );
};

export default ContentLayout;
