// Main layout component that wraps pages with Sidebar and Header

import React, { useState } from 'react';
import { Grid, GridItem, Box } from '@chakra-ui/react';
import Sidebar from './Sidebar';
import Header from './Header';

interface LayoutProps {
  children: React.ReactNode;
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const [isSidebarBlurred, setIsSidebarBlurred] = useState(false);

  const handleSidebarHover = (isHovered: boolean) => {
    setIsSidebarBlurred(isHovered);
  };

  return (
    <Grid
      templateAreas="'nav main'"
      gridTemplateColumns="4.5rem 1fr"
      minH="100vh"
      h="100%"
      gap={0}
      sx={{
        minHeight: '100dvh',
        height: '100%',
      }}
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

      {/* Main Content: scroll when content overflows (vertical + horizontal) so nothing is trimmed */}
      <GridItem
        area="main"
        overflow="auto"
        display="flex"
        flexDirection="column"
        minH={0}
        minW={0}
        sx={{ minHeight: '200px' }}
      >
        <Box
          opacity={isSidebarBlurred ? 0.3 : 1}
          transition="opacity 0.2s"
          flex="1"
          minH={0}
          minW={0}
          display="flex"
          flexDirection="column"
          bg="gray.50"
        >
          <Header />
          <Box
            as="main"
            p={4}
            flex="1"
            minH={0}
            minW={0}
            overflow="auto"
            display="flex"
            flexDirection="column"
          >
            {children}
          </Box>
        </Box>
      </GridItem>
    </Grid>
  );
};

export default Layout;