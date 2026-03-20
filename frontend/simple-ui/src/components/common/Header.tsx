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
import { getServiceTitle, type ServiceId } from "../../config/serviceMetadata";
import { useAuth } from "../../hooks/useAuth";
import { useSessionExpiry } from "../../hooks/useSessionExpiry";
import AuthModal from "../auth/AuthModal";
import ApiKeyViewerModal from "./ApiKeyViewerModal";

const PATH_TO_SERVICE: Record<string, ServiceId> = {
  "/asr": "asr",
  "/tts": "tts",
  "/nmt": "nmt",
  "/llm": "llm",
  "/pipeline": "pipeline",
  "/ocr": "ocr",
  "/transliteration": "transliteration",
  "/language-detection": "language-detection",
  "/speaker-diarization": "speaker-diarization",
  "/language-diarization": "language-diarization",
  "/audio-language-detection": "audio-language-detection",
  "/ner": "ner",
};

const Header: React.FC = () => {
  const router = useRouter();
  const {
    isAuthenticated: isUserAuthenticated,
    user,
    isLoading: isAuthLoading,
    logout,
  } = useAuth();
  const { checkSessionExpiry } = useSessionExpiry();

  const [isApiKeyViewerOpen, setIsApiKeyViewerOpen] = useState(false);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [title, setTitle] = useState("");

  // Determine if we should show user menu or sign in button
  const showUserMenu =
    !isAuthLoading && isUserAuthenticated && user && user.username;

  // Check session expiry on mount and when user changes
  useEffect(() => {
    if (isUserAuthenticated && !isAuthLoading) {
      checkSessionExpiry();
    }
  }, [isUserAuthenticated, isAuthLoading, checkSessionExpiry]);

  // Periodic session expiry check (every 60 seconds)
  useEffect(() => {
    if (!isUserAuthenticated || isAuthLoading) {
      return;
    }

    const intervalId = setInterval(() => {
      checkSessionExpiry();
    }, 60000); // Check every 60 seconds

    return () => clearInterval(intervalId);
  }, [isUserAuthenticated, isAuthLoading, checkSessionExpiry]);

  // Update title based on route (service pages use serviceMetadata; others use fixed labels)
  useEffect(() => {
    const pathname = router.pathname;
    const serviceId = PATH_TO_SERVICE[pathname];
    if (serviceId) {
      setTitle(getServiceTitle(serviceId));
      return;
    }
    switch (pathname) {
      case "/pipeline-builder":
        setTitle("Pipeline Builder");
        break;
      case "/profile":
        setTitle("Profile");
        break;
      case "/model-management":
        setTitle("Model Management");
        break;
      case "/services-management":
        setTitle("Services Management");
        break;
      case "/tenant-management":
        setTitle("Tenant Management");
        break;
      case "/auth":
        setTitle("Sign In");
        break;
      case "/":
        setTitle("");
        break;
      default:
        setTitle("");
    }
  }, [router.pathname]);

  const bgColor = useColorModeValue("white", "gray.800");
  const borderColor = useColorModeValue("gray.200", "gray.700");
  const showBackButton = router.pathname !== "/";

  const handleBack = () => {
    if (router.pathname === "/services-management" && router.query.tab === "2") {
      router.push("/services-management");
      return;
    }
    if (router.pathname === "/tenant-management") {
      router.push("/");
      return;
    }
    if (router.pathname === "/model-management" && router.query.tab === "2") {
      router.push("/model-management");
      return;
    }
    router.push("/");
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
                  <MenuItem onClick={() => {
                    // Check session expiry before navigating to profile
                    if (!checkSessionExpiry()) return;
                    router.push("/profile");
                  }}>
                    Profile
                  </MenuItem>
                  {/* <MenuItem onClick={() => {
                    // Check session expiry before opening API Key viewer
                    if (!checkSessionExpiry()) return;
                    setIsApiKeyViewerOpen(true);
                  }}>
                    API Key
                  </MenuItem> */}
                  <MenuItem onClick={async () => {
                    // Check session expiry before logout
                    if (!checkSessionExpiry()) return;
                    await logout();
                  }}>Sign out</MenuItem>
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
