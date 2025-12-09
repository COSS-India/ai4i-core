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

const AuthPage: React.FC = () => {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");

  // Redirect to home if already authenticated
  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      router.push("/");
    }
  }, [isAuthenticated, isLoading, router]);

  // Get initial mode from query parameter
  useEffect(() => {
    const { mode: queryMode } = router.query;
    if (queryMode === "register" || queryMode === "signup") {
      setMode("register");
    } else {
      setMode("login");
    }
  }, [router.query]);

  // Handle successful login - redirect to home or intended destination
  const handleLoginSuccess = () => {
    // Check if there's a redirect destination stored
    if (typeof window !== 'undefined') {
      const redirectPath = sessionStorage.getItem('redirectAfterAuth');
      if (redirectPath) {
        sessionStorage.removeItem('redirectAfterAuth');
        router.push(redirectPath);
      } else {
        router.push("/");
      }
    } else {
      router.push("/");
    }
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
        bg={useColorModeValue("gray.50", "gray.900")}
        display="flex"
        alignItems="center"
        justifyContent="center"
        py={8}
        px={4}
      >
        <Container maxW="md">
          <VStack spacing={8}>
            <Heading size="xl" color="gray.800" textAlign="center">
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
                      />
                    </TabPanel>

                    <TabPanel px={6} py={6}>
                      <RegisterForm
                        onSuccess={handleLoginSuccess}
                        onSwitchToLogin={switchToLogin}
                        onRegisterSuccess={handleRegisterSuccess}
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

