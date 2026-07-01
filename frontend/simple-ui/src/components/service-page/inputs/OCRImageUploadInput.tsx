import React from "react";
import {
  Box,
  Button,
  FormControl,
  FormLabel,
  HStack,
  Icon,
  IconButton,
  Input,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  Text,
  VStack,
} from "@chakra-ui/react";
import { AttachmentIcon, DeleteIcon } from "@chakra-ui/icons";
import { FaUpload } from "react-icons/fa";

interface OCRImageUploadInputProps {
  imageFile: File | null;
  imageUri: string;
  activeTab: number;
  isDragging: boolean;
  blockMediaInput: boolean;
  fileInputRef: React.Ref<HTMLInputElement>;
  onTabChange: (index: number) => void;
  onFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onDragOver: (e: React.DragEvent) => void;
  onDragLeave: (e: React.DragEvent) => void;
  onDrop: (e: React.DragEvent) => void;
  onFileButtonClick: () => void;
  onRemoveFile: () => void;
  onUriChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
}

interface DropZoneProps {
  isDragging: boolean;
  blockMediaInput: boolean;
  onDragOver: (e: React.DragEvent) => void;
  onDragLeave: (e: React.DragEvent) => void;
  onDrop: (e: React.DragEvent) => void;
  onFileButtonClick: () => void;
}

const OCRDropZone: React.FC<DropZoneProps> = ({
  isDragging,
  blockMediaInput,
  onDragOver,
  onDragLeave,
  onDrop,
  onFileButtonClick,
}) => {
  const enabled = !blockMediaInput;

  return (
    <Box
      onDragOver={enabled ? onDragOver : undefined}
      onDragLeave={enabled ? onDragLeave : undefined}
      onDrop={enabled ? onDrop : undefined}
      border="2px dashed"
      borderColor={isDragging ? "teal.400" : "gray.300"}
      borderRadius="lg"
      p={8}
      textAlign="center"
      bg={isDragging ? "teal.50" : "gray.50"}
      cursor={enabled ? "pointer" : "not-allowed"}
      opacity={enabled ? 1 : 0.6}
      transition="all 0.2s"
      _hover={enabled ? { borderColor: "teal.400", bg: "teal.50" } : {}}
      onClick={enabled ? onFileButtonClick : undefined}
    >
      <VStack spacing={4}>
        <Icon as={AttachmentIcon} boxSize={10} color={isDragging ? "teal.500" : "gray.400"} />
        <Text fontSize="md" fontWeight="semibold" color="gray.700">
          {isDragging ? "Drop image here" : "Click to upload or drag and drop"}
        </Text>
        <Button
          size="sm"
          colorScheme="teal"
          leftIcon={<FaUpload />}
          isDisabled={blockMediaInput}
          onClick={(e) => {
            e.stopPropagation();
            onFileButtonClick();
          }}
        >
          Upload Image
        </Button>
      </VStack>
    </Box>
  );
};

const OCRSelectedFile: React.FC<{ file: File; onRemove: () => void }> = ({ file, onRemove }) => (
  <Box border="2px solid" borderColor="green.300" borderRadius="lg" p={4} bg="green.50">
    <HStack justify="space-between" align="center">
      <HStack spacing={3} flex={1}>
        <Icon as={AttachmentIcon} boxSize={6} color="green.600" />
        <VStack align="start" spacing={0} flex={1} minW={0}>
          <Text fontSize="sm" fontWeight="semibold" color="green.800" isTruncated>
            {file.name}
          </Text>
          <Text fontSize="xs" color="green.600">
            {(file.size / 1024 / 1024).toFixed(2)} MB
          </Text>
        </VStack>
      </HStack>
      <IconButton
        aria-label="Remove file"
        icon={<DeleteIcon />}
        size="sm"
        variant="ghost"
        colorScheme="red"
        onClick={onRemove}
      />
    </HStack>
  </Box>
);

const OCRImageUploadInput: React.FC<OCRImageUploadInputProps> = (props) => {
  const {
    imageFile,
    imageUri,
    activeTab,
    isDragging,
    blockMediaInput,
    fileInputRef,
    onTabChange,
    onFileChange,
    onDragOver,
    onDragLeave,
    onDrop,
    onFileButtonClick,
    onRemoveFile,
    onUriChange,
  } = props;

  return (
    <FormControl>
      <FormLabel fontSize="sm" fontWeight="semibold">
        Upload Image for OCR <Text as="span" color="red.500">*</Text>
      </FormLabel>

      <Tabs index={activeTab} onChange={onTabChange} mb={4}>
        <TabList>
          <Tab fontSize="sm">Upload File</Tab>
          <Tab fontSize="sm">Image URL</Tab>
        </TabList>
        <TabPanels>
          <TabPanel px={0}>
            <Text fontSize="xs" color="gray.500" mb={3}>
              Supported formats: PNG, JPG, JPEG, WebP (Max size: 10MB)
            </Text>
            <Input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={onFileChange}
              isDisabled={blockMediaInput}
              display="none"
            />
            {imageFile ? (
              <OCRSelectedFile file={imageFile} onRemove={onRemoveFile} />
            ) : (
              <OCRDropZone
                isDragging={isDragging}
                blockMediaInput={blockMediaInput}
                onDragOver={onDragOver}
                onDragLeave={onDragLeave}
                onDrop={onDrop}
                onFileButtonClick={onFileButtonClick}
              />
            )}
          </TabPanel>
          <TabPanel px={0}>
            <Input
              type="url"
              value={imageUri}
              onChange={onUriChange}
              placeholder="https://example.com/image.jpg"
              isDisabled={blockMediaInput}
              size="md"
              borderColor="gray.300"
              _focus={{
                borderColor: "teal.400",
                boxShadow: "0 0 0 1px var(--chakra-colors-teal-400)",
              }}
            />
          </TabPanel>
        </TabPanels>
      </Tabs>
    </FormControl>
  );
};

export default OCRImageUploadInput;
