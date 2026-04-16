/**
 * Authentication modal component with Chakra UI
 */
import React, { useState } from "react";
import { useAuth } from "../../hooks/useAuth";
import LoginForm from "./LoginForm";
import RegisterForm from "./RegisterForm";
import StandardModal from "../common/StandardModal";

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
    <StandardModal
      isOpen={isOpen}
      onClose={onClose}
      size="md"
      title=""
      hideHeader
      bodyProps={{ pb: 6 }}
      hideCloseButton={false}
      overlayProps={{ bg: "blackAlpha.300", backdropFilter: "blur(10px)", zIndex: 1400 }}
      contentProps={{ zIndex: 1500 }}
      footer={undefined}
    >
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
    </StandardModal>
  );
};

export default AuthModal;
