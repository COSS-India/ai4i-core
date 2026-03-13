// Main layout component that wraps pages with Sidebar and Header

import React, { useState } from 'react';
import { Grid, GridItem, Box, useMediaQuery } from '@chakra-ui/react';
import Sidebar from './Sidebar';
import Header from './Header';

interface LayoutProps {
  children: React.ReactNode;
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const [isSidebarBlurred, setIsSidebarBlurred] = useState(false);
  const [isMobile] = useMediaQuery('(max-width: 1080px)');

  const handleSidebarHover = (isHovered: boolean) => {
    setIsSidebarBlurred(isHovered);
  };

  if (isMobile) {
    // Mobile layout - no sidebar
    return (
      <Box minH="100vh" bg="gray.50">
        <Header />
        <Box as="main" p={4}>
          {children}
        </Box>
      </Box>
    );
  }

  // Desktop layout
  return (
    <Grid
      templateAreas="'nav main'"
      gridTemplateColumns="95px 1fr"
      h="100vh"
      gap={0}
    >
      {/* Sidebar */}
      <GridItem area="nav">
        <Box
          onMouseEnter={() => handleSidebarHover(true)}
          onMouseLeave={() => handleSidebarHover(false)}
        >
          <Sidebar />
        </Box>
      </GridItem>

      {/* Main Content - no outer scroll; only inner content scrolls */}
      <GridItem area="main" overflow="hidden" display="flex" flexDirection="column" minH={0}>
        <Box
          opacity={isSidebarBlurred ? 0.3 : 1}
          transition="opacity 0.2s"
          flex="1"
          minH={0}
          display="flex"
          flexDirection="column"
          bg="gray.50"
        >
          <Header />
          <Box as="main" p={4} flex="1" minH={0} overflow="hidden" display="flex" flexDirection="column">
            {children}
          </Box>
        </Box>
      </GridItem>
    </Grid>
  );
};

export default Layout;