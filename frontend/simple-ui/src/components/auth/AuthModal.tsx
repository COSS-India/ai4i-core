/**
 * Authentication modal component with Chakra UI
 */
import {
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalOverlay,
} from "@chakra-ui/react";
import React, { useState } from "react";
import { useAuth } from "../../hooks/useAuth";
import LoginForm from "./LoginForm";
import RegisterForm from "./RegisterForm";

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialMode?: "login" | "register";
}

const AuthModal: React.FC<AuthModalProps> = ({
  isOpen,
  onClose,
  initialMode = "login",
}) => {
  const [mode, setMode] = useState<"login" | "register">(initialMode);
  const { isAuthenticated, isLoading } = useAuth();

  // Close modal if user becomes authenticated (backup in case handleSuccess wasn't called)
  React.useEffect(() => {
    console.log("AuthModal: State check", {
      isAuthenticated,
      isLoading,
      isOpen,
    });
    if (!isLoading && isAuthenticated && isOpen) {
      console.log("AuthModal: ✅ User authenticated (backup), closing modal");
      // Close immediately - no delay needed
      // This is a backup in case handleSuccess callback wasn't triggered
      onClose();
    }
  }, [isAuthenticated, isLoading, isOpen, onClose]);

  const handleSuccess = () => {
    // Close modal immediately after successful login
    // The useEffect will also handle it as a backup, but this ensures immediate response
    console.log("AuthModal: handleSuccess called, closing modal immediately");
    onClose();
  };

  const switchToLogin = () => {
    setMode("login");
  };

  const switchToRegister = () => {
    setMode("register");
  };

  const handleRegisterSuccess = () => {
    // After successful registration, switch to login page
    setMode("login");
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size="md"
      isCentered
      closeOnOverlayClick={true}
    >
      <ModalOverlay
        bg="blackAlpha.300"
        backdropFilter="blur(10px)"
        zIndex={1400}
      />
      <ModalContent zIndex={1500}>
        {/* <ModalHeader>
          {mode === 'login' ? 'Sign In' : 'Sign Up'}
        </ModalHeader> */}
        <ModalCloseButton />
        <ModalBody pb={6}>
          {mode === "login" ? (
            <LoginForm
              onSuccess={handleSuccess}
              onSwitchToRegister={switchToRegister}
            />
          ) : (
            <RegisterForm
              onSuccess={handleSuccess}
              onSwitchToLogin={switchToLogin}
              onRegisterSuccess={handleRegisterSuccess}
            />
          )}
        </ModalBody>
      </ModalContent>
    </Modal>
  );
};

export default AuthModal;
