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

      {/* Main Content */}
      <GridItem area="main" overflow="auto">
        <Box
          opacity={isSidebarBlurred ? 0.3 : 1}
          transition="opacity 0.2s"
          minH="100vh"
          bg="gray.50"
        >
          <Header />
          <Box as="main" p={4}>
            {children}
          </Box>
        </Box>
      </GridItem>
    </Grid>
  );
};

export default Layout;