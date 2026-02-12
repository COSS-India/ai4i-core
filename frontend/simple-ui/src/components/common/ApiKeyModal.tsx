// Modal component for API key input and management

import React, { useState } from 'react';
import {
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalFooter,
  ModalBody,
  ModalCloseButton,
  Button,
  FormControl,
  FormLabel,
  Input,
  FormErrorMessage,
  InputGroup,
  InputRightElement,
  IconButton,
} from '@chakra-ui/react';
import { ViewIcon, ViewOffIcon } from '@chakra-ui/icons';
import { useApiKey } from '../../hooks/useApiKey';
import { useToastWithDeduplication } from '../../hooks/useToastWithDeduplication';

interface ApiKeyModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const ApiKeyModal: React.FC<ApiKeyModalProps> = ({ isOpen, onClose }) => {
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const { setApiKey } = useApiKey();
  const toast = useToastWithDeduplication();

  const handleSave = async () => {
    setError(null);
    setIsLoading(true);

    try {
      // Validate input
      if (!apiKeyInput.trim()) {
        setError('API key is required');
        return;
      }

      if (apiKeyInput.length < 20) {
        setError('API key must be at least 20 characters long');
        return;
      }

      // Set API key
      setApiKey(apiKeyInput.trim());
      
      // Show success toast
      toast({
        title: 'API Key Saved',
        description: 'Your API key has been saved successfully.',
        status: 'success',
        duration: 3000,
        isClosable: true,
      });

      // Close modal and reset form
      onClose();
      setApiKeyInput('');
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save API key');
    } finally {
      setIsLoading(false);
    }
  };

  const handleClose = () => {
    setApiKeyInput('');
    setError(null);
    onClose();
  };

  const toggleShowApiKey = () => {
    setShowApiKey(!showApiKey);
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} size="md" isCentered>
      <ModalOverlay />
      <ModalContent>
        <ModalHeader>Enter API Key</ModalHeader>
        <ModalCloseButton />
        
        <ModalBody pb={6}>
          <FormControl isInvalid={!!error}>
            <FormLabel>API Key</FormLabel>
            <InputGroup>
              <Input
                type={showApiKey ? 'text' : 'password'}
                placeholder="Enter your API key"
                value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
                isDisabled={isLoading}
              />
              <InputRightElement>
                <IconButton
                  aria-label={showApiKey ? 'Hide API key' : 'Show API key'}
                  icon={showApiKey ? <ViewOffIcon /> : <ViewIcon />}
                  onClick={toggleShowApiKey}
                  variant="ghost"
                  size="sm"
                />
              </InputRightElement>
            </InputGroup>
            <FormErrorMessage>{error}</FormErrorMessage>
          </FormControl>
        </ModalBody>

        <ModalFooter>
          <Button variant="ghost" mr={3} onClick={handleClose} isDisabled={isLoading}>
            Cancel
          </Button>
          <Button
            colorScheme="orange"
            onClick={handleSave}
            isLoading={isLoading}
            loadingText="Saving..."
          >
            Save
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

export default ApiKeyModal;