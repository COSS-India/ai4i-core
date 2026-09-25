import { ChevronDownIcon } from "@chakra-ui/icons";
import {
  Avatar,
  Box,
  Button,
  HStack,
  Menu,
  MenuButton,
  MenuGroup,
  MenuItem,
  MenuList,
  Text,
  useColorModeValue,
} from "@chakra-ui/react";
import { useRouter } from "next/router";
import React, { useEffect, useState } from "react";
import { useAuth } from "../../hooks/useAuth";
import { useSessionExpiry } from "../../hooks/useSessionExpiry";
import { getPlatformName } from "../../config/runtimeConfig";
import {
  canSeeOnboardingGuide,
  getOnboardingGuideHref,
  getPreLoginGuideOptions,
} from "../../config/onboardingGuide";
import { getHomePath } from "../../utils/navigation";
import AuthModal from "../auth/AuthModal";

const Header: React.FC = () => {
  const router = useRouter();
  const {
    isAuthenticated: isUserAuthenticated,
    user,
    isLoading: isAuthLoading,
    logout,
  } = useAuth();
  const { checkSessionExpiry } = useSessionExpiry();

  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);

  const showUserMenu =
    !isAuthLoading && isUserAuthenticated && !!user;

  const profileDisplayName =
    (user?.full_name ?? "").trim() || "N/A";
  const showOnboardingGuideMenu =
    showUserMenu && canSeeOnboardingGuide(user?.roles);
  const onboardingGuideHref = getOnboardingGuideHref(user?.roles);
  const preLoginGuideOptions = getPreLoginGuideOptions();
  const showHomeOnboardingGuideLink =
    !showUserMenu && router.pathname === "/";

  useEffect(() => {
    if (isUserAuthenticated && !isAuthLoading) {
      checkSessionExpiry();
    }
  }, [isUserAuthenticated, isAuthLoading, checkSessionExpiry]);

  useEffect(() => {
    if (!isUserAuthenticated || isAuthLoading) {
      return;
    }

    const intervalId = setInterval(() => {
      checkSessionExpiry();
    }, 60000);

    return () => clearInterval(intervalId);
  }, [isUserAuthenticated, isAuthLoading, checkSessionExpiry]);

  const bgColor = useColorModeValue("white", "gray.800");
  const borderColor = useColorModeValue("ink.200", "gray.700");
  const homePath = getHomePath(user?.roles);

  const handleAuthClick = () => {
    router.push("/auth");
  };

  return (
    <>
      <Box
        h="3.5rem"
        bg={bgColor}
        px={6}
        flexShrink={0}
        borderBottom="1px"
        borderColor={borderColor}
        position="sticky"
        top={0}
        zIndex={50}
      >
        <HStack justify="space-between" h="full" spacing={4}>
          <Text fontSize="sm" fontWeight="600" color="ink.800" noOfLines={1} letterSpacing="-0.01em">
            {getPlatformName()}
          </Text>

          <HStack spacing={3}>
            {showUserMenu ? (
              <Menu placement="bottom-end">
                <MenuButton
                  as={Button}
                  variant="ghost"
                  size="sm"
                  rightIcon={<ChevronDownIcon />}
                  px={2}
                  h="2.5rem"
                >
                  <HStack spacing={2}>
                    <Avatar
                      size="sm"
                      name={
                        profileDisplayName !== "N/A"
                          ? profileDisplayName
                          : user?.username || "User"
                      }
                      bg="ink.700"
                      color="white"
                      getInitials={(name) => name.trim().charAt(0).toUpperCase()}
                    />
                    <Text
                      fontSize="sm"
                      fontWeight="600"
                      color="ink.700"
                      noOfLines={1}
                      maxW="10rem"
                      display={{ base: "none", md: "block" }}
                    >
                      {profileDisplayName}
                    </Text>
                  </HStack>
                </MenuButton>
                <MenuList minW="12rem">
                  <MenuItem
                    onClick={() => {
                      if (!checkSessionExpiry()) return;
                      router.push("/profile");
                    }}
                  >
                    Profile
                  </MenuItem>
                  {showOnboardingGuideMenu && (
                    <MenuItem
                      onClick={() => {
                        if (!checkSessionExpiry()) return;
                        window.open(onboardingGuideHref, "_blank", "noopener,noreferrer");
                      }}
                    >
                      Onboarding guide
                    </MenuItem>
                  )}
                  <MenuItem
                    onClick={async () => {
                      if (!checkSessionExpiry()) return;
                      await logout();
                      router.push(homePath);
                    }}
                  >
                    Sign out
                  </MenuItem>
                </MenuList>
              </Menu>
            ) : (
              <HStack spacing={3}>
                {showHomeOnboardingGuideLink && (
                  <Menu placement="bottom-end">
                    <MenuButton
                      as={Button}
                      variant="ghost"
                      size="sm"
                      rightIcon={<ChevronDownIcon />}
                    >
                      Onboarding guide
                    </MenuButton>
                    <MenuList minW="16rem">
                      <MenuGroup title="Select your guide">
                        {preLoginGuideOptions.map((option) => (
                          <MenuItem
                            key={option.href}
                            as="a"
                            href={option.href}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            {option.label}
                          </MenuItem>
                        ))}
                      </MenuGroup>
                    </MenuList>
                  </Menu>
                )}
                <Button
                  colorScheme="ink"
                  variant="solid"
                  size="sm"
                  onClick={handleAuthClick}
                >
                  Sign in
                </Button>
              </HStack>
            )}
          </HStack>
        </HStack>
      </Box>

      <AuthModal
        isOpen={isAuthModalOpen}
        onClose={() => setIsAuthModalOpen(false)}
        initialMode="login"
      />
    </>
  );
};

export default Header;
