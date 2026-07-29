// Authentication page with sign in and sign up tabs

import {
  Box,
  Card,
  CardBody,
  Heading,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
  useColorModeValue,
  Container,
  VStack,
} from "@chakra-ui/react";
import Head from "next/head";
import { useRouter } from "next/router";
import React, { useEffect, useState } from "react";
import { useAuth } from "../hooks/useAuth";
import LoginForm from "../components/auth/LoginForm";
import RegisterForm from "../components/auth/RegisterForm";
import { ACCOUNT_DELETED_LOGIN_MESSAGE } from "../components/profile/hooks/useDeleteAccount";
import { getDefaultLandingPath } from "../utils/navigation";

const AuthPage: React.FC = () => {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");
  const pageBg = useColorModeValue("gray.50", "gray.900");

  // Allow only same-origin relative paths to prevent open redirects
  const isSafeRelativePath = (path: string): boolean => {
    if (typeof path !== "string" || path.length === 0) return false;
    if (!path.startsWith("/")) return false;
    if (path.startsWith("//")) return false;
    return true;
  };

  const getRedirectPath = (): string => {
    const redirect = router.query.redirect;
    const path = typeof redirect === "string" ? redirect : "";
    // Prefer explicit redirect; otherwise Usage Dashboard (or services home if unauthorized).
    // Omit roles so getDefaultLandingPath reads stored user when React state has not flushed yet.
    // To restore previous post-login landing (services home `/`), use:
    // return isSafeRelativePath(path) ? path : "/";
    return isSafeRelativePath(path) ? path : getDefaultLandingPath();
  };

  // Redirect to home or intended destination if already authenticated
  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      router.push(getRedirectPath());
    }
  }, [isAuthenticated, isLoading, router, router.query]);

  // Get initial mode from query parameter
  useEffect(() => {
    const { mode: queryMode } = router.query;
    if (queryMode === "register" || queryMode === "signup") {
      setMode("register");
    } else {
      setMode("login");
    }
  }, [router.query]);

  const [bannerDismissed, setBannerDismissed] = useState(false);

  useEffect(() => {
    if (router.isReady && router.query.message === "account-deleted") {
      setBannerDismissed(false);
    }
  }, [router.isReady, router.query.message]);

  const loginBannerMessage =
    !bannerDismissed && router.isReady && router.query.message === "account-deleted"
      ? ACCOUNT_DELETED_LOGIN_MESSAGE
      : null;

  const dismissLoginBanner = async () => {
    setBannerDismissed(true);
    if (!router.isReady || router.query.message !== "account-deleted") return;

    const { message: _message, ...rest } = router.query;
    await router.replace({ pathname: router.pathname, query: rest }, undefined, { shallow: true });
  };

  // Handle successful login - redirect to intended destination or default landing
  const handleLoginSuccess = () => {
    router.push(getRedirectPath());
  };

  // Handle successful registration - switch to login tab
  const handleRegisterSuccess = () => {
    setMode("login");
  };

  // Switch to login tab
  const switchToLogin = () => {
    setMode("login");
  };

  // Switch to register tab
  const switchToRegister = () => {
    setMode("register");
  };

  // Show loading spinner while checking authentication
  if (isLoading) {
    return null; // Or show a loading spinner
  }

  // Don't render if authenticated (will redirect)
  if (isAuthenticated) {
    return null;
  }

  return (
    <>
      <Head>
        <title>Sign In - AI4I Platform</title>
        <meta name="description" content="Sign in or sign up to access AI4I Platform" />
      </Head>

      <Box
        minH="100vh"
        bg={pageBg}
        display="flex"
        alignItems="center"
        justifyContent="center"
        py={8}
        px={4}
      >
        <Container maxW="md">
          <VStack spacing={8}>
            <Heading size="xl" color="gray.800" textAlign="center" userSelect="none" cursor="default" tabIndex={-1}>
              AI4I Platform
            </Heading>

            <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" w="full" boxShadow="lg">
              <CardBody p={0}>
                <Tabs
                  index={mode === "login" ? 0 : 1}
                  onChange={(index) => setMode(index === 0 ? "login" : "register")}
                  colorScheme="blue"
                  variant="enclosed"
                >
                  <TabList>
                    <Tab fontWeight="semibold" flex={1}>
                      Sign In
                    </Tab>
                    <Tab fontWeight="semibold" flex={1}>
                      Sign Up
                    </Tab>
                  </TabList>

                  <TabPanels>
                    <TabPanel px={6} py={6}>
                      <LoginForm
                        onSuccess={handleLoginSuccess}
                        onSwitchToRegister={switchToRegister}
                        bannerMessage={loginBannerMessage}
                        onDismissBanner={dismissLoginBanner}
                      />
                    </TabPanel>

                    <TabPanel px={6} py={6}>
                      <RegisterForm
                        onSuccess={handleLoginSuccess}
                        onSwitchToLogin={switchToLogin}
                        onRegisterSuccess={handleRegisterSuccess}
                        isActive={mode === "register"}
                      />
                    </TabPanel>
                  </TabPanels>
                </Tabs>
              </CardBody>
            </Card>
          </VStack>
        </Container>
      </Box>
    </>
  );
};

export default AuthPage;
