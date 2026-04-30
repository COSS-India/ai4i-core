import React, { useState } from 'react';
import {
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalCloseButton,
  ModalBody,
  ModalFooter,
  Button,
  FormControl,
  FormLabel,
  Input,
  InputGroup,
  InputRightElement,
  IconButton,
  Text,
} from '@chakra-ui/react';
import { ViewIcon, ViewOffIcon } from '@chakra-ui/icons';
import { useApiKey } from '../../hooks/useApiKey';

interface ApiKeyViewerModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const ApiKeyViewerModal: React.FC<ApiKeyViewerModalProps> = ({ isOpen, onClose }) => {
  const { apiKey } = useApiKey();
  const [showApiKey, setShowApiKey] = useState(false);

  const masked = apiKey ? '****' + apiKey.slice(-4) : '';

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="md" isCentered>
      <ModalOverlay />
      <ModalContent>
        <ModalHeader>API Key</ModalHeader>
        <ModalCloseButton />
        <ModalBody pb={6}>
          {apiKey ? (
            <FormControl>
              <FormLabel>Current API Key</FormLabel>
              <InputGroup>
                <Input
                  type={showApiKey ? 'text' : 'password'}
                  value={showApiKey ? apiKey : masked}
                  isReadOnly
                />
                <InputRightElement>
                  <IconButton
                    aria-label={showApiKey ? 'Hide API key' : 'Show API key'}
                    icon={showApiKey ? <ViewOffIcon /> : <ViewIcon />}
                    onClick={() => setShowApiKey(v => !v)}
                    variant="ghost"
                    size="sm"
                  />
                </InputRightElement>
              </InputGroup>
            </FormControl>
          ) : (
            <Text color="gray.600">API key not set.</Text>
          )}
        </ModalBody>
        <ModalFooter>
          <Button onClick={onClose}>Close</Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

export default ApiKeyViewerModal;


