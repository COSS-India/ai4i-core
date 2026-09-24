// Main layout component that wraps pages with Sidebar and Header

import React from 'react';
import { Grid, GridItem, Box } from '@chakra-ui/react';
import Sidebar from './Sidebar';
import Header from './Header';
import {
  SIDEBAR_COLLAPSED_WIDTH,
  SIDEBAR_EXPANDED_WIDTH,
  useSidebarPin,
} from '../../hooks/useSidebarPin';

interface LayoutProps {
  children: React.ReactNode;
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const { pinned, togglePinned } = useSidebarPin();

  return (
    <Grid
      templateAreas="'nav main'"
      gridTemplateColumns={`${pinned ? SIDEBAR_EXPANDED_WIDTH : SIDEBAR_COLLAPSED_WIDTH} 1fr`}
      minH="100vh"
      h="100%"
      gap={0}
      transition="grid-template-columns 0.2s ease"
      sx={{
        minHeight: '100dvh',
        height: '100%',
      }}
    >
      <GridItem area="nav">
        <Sidebar pinned={pinned} onTogglePin={togglePinned} />
      </GridItem>

      <GridItem
        area="main"
        overflow="hidden"
        display="flex"
        flexDirection="column"
        minH={0}
        minW={0}
        bg="light.100"
      >
        <Header />
        <Box
          as="main"
          flex="1"
          minH={0}
          minW={0}
          overflow="auto"
          display="flex"
          flexDirection="column"
        >
          {children}
        </Box>
      </GridItem>
    </Grid>
  );
};

export default Layout;
