// Header/navbar component for top navigation with authentication and API key management

import { ArrowBackIcon, HamburgerIcon } from "@chakra-ui/icons";
import {
  Badge,
  Box,
  Button,
  HStack,
  Heading,
  IconButton,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
  useColorModeValue,
} from "@chakra-ui/react";
import { useRouter } from "next/router";
import React, { useEffect, useState } from "react";
import { useAuth } from "../../hooks/useAuth";
import AuthModal from "../auth/AuthModal";
import ApiKeyViewerModal from "./ApiKeyViewerModal";

const Header: React.FC = () => {
  const router = useRouter();
  const {
    isAuthenticated: isUserAuthenticated,
    user,
    isLoading: isAuthLoading,
    logout,
  } = useAuth();

  const [isApiKeyViewerOpen, setIsApiKeyViewerOpen] = useState(false);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [title, setTitle] = useState("Dashboard");

  // Determine if we should show user menu or sign in button
  const showUserMenu =
    !isAuthLoading && isUserAuthenticated && user && user.username;

  // Update title based on route
  useEffect(() => {
    const pathname = router.pathname;
    switch (pathname) {
      case "/asr":
        setTitle("ASR – Automatic Speech Recognition");
        break;
      case "/tts":
        setTitle("TTS – Text-to-Speech");
        break;
      case "/nmt":
        setTitle("Text Translation");
        break;
      case "/llm":
        setTitle("Large Language Model");
        break
      case "/pipeline":
        setTitle("Speech-to-Speech Pipeline");
        break;
      case "/pipeline-builder":
        setTitle("Pipeline Builder");
        break;
      case "/profile":
        setTitle("Profile");
        break;
      case "/model-management":
        setTitle("Model Management");
        break;
      case "/auth":
        setTitle("Sign In");
        break;
      case "/":
        setTitle("AI4Inclusion Console");
        break;
      default:
        setTitle("AI4Inclusion Console");
    }
  }, [router.pathname]);

  const bgColor = useColorModeValue("white", "gray.800");
  const borderColor = useColorModeValue("gray.200", "gray.700");
  const showBackButton = router.pathname !== "/";

  const handleBack = () => {
    if (router.pathname === "/pipeline-builder") {
      router.push("/");
    } else {
      router.back();
    }
  };

  const handleAuthClick = () => {
    console.log("Header: Sign In button clicked, redirecting to /auth");
    router.push("/auth");
  };

  // Debug: Log AuthModal state
  useEffect(() => {
    console.log("Header: AuthModal state:", { isAuthModalOpen });
  }, [isAuthModalOpen]);

  return (
    <>
      <Box
        h="3.5rem"
        bg={bgColor}
        pl="calc(4.5rem + 1.5rem)"
        pr="1.5rem"
        boxShadow="sm"
        position="fixed"
        top={0}
        left={0}
        right={0}
        zIndex={50}
        borderBottom="1px"
        borderColor={borderColor}
      >
        <HStack justify="space-between" h="full">
          {/* Left side - Back button, Logo and Page title */}
          <HStack spacing={3}>
            {showBackButton && (
              <IconButton
                aria-label="Go back"
                icon={<ArrowBackIcon />}
                variant="ghost"
                size="sm"
                onClick={handleBack}
                colorScheme="gray"
                _hover={{ bg: "gray.100" }}
              />
            )}
            <Heading size="md" color="gray.800">
              {title}
            </Heading>
          </HStack>

          {/* Right side - Menu and Auth */}
          <HStack spacing={4}>
            {/* Authentication: Show username badge or Sign In button */}
            {showUserMenu ? (
              <Badge
                colorScheme="gray"
                fontSize="sm"
                px={3}
                py={1}
                borderRadius="md"
              >
                {user.username}
              </Badge>
            ) : (
              <Button
                colorScheme="blue"
                variant="outline"
                size="sm"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  console.log("Header: Sign In button clicked");
                  handleAuthClick();
                }}
              >
                Sign In
              </Button>
            )}

            {/* Menu */}
            {showUserMenu && (
              <Menu>
                <MenuButton
                  as={IconButton}
                  aria-label="Options"
                  icon={<HamburgerIcon />}
                  variant="ghost"
                  size="sm"
                />
                <MenuList>
                  <MenuItem onClick={() => router.push("/profile")}>
                    Profile
                  </MenuItem>
                  {/* <MenuItem onClick={() => setIsApiKeyViewerOpen(true)}>
                    API Key
                  </MenuItem> */}
                  <MenuItem onClick={() => logout()}>Sign out</MenuItem>
                </MenuList>
              </Menu>
            )}
          </HStack>
        </HStack>
      </Box>

      {/* API Key Viewer Modal */}
      <ApiKeyViewerModal
        isOpen={isApiKeyViewerOpen}
        onClose={() => setIsApiKeyViewerOpen(false)}
      />

      {/* Auth Modal */}
      <AuthModal
        isOpen={isAuthModalOpen}
        onClose={() => {
          console.log("Header: Closing AuthModal");
          setIsAuthModalOpen(false);
        }}
        initialMode="login"
      />
    </>
  );
};

export default Header;
