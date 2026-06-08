import React from "react";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  FormControl,
  FormLabel,
  Heading,
  HStack,
  Input,
  Select,
  SimpleGrid,
  Text,
  Textarea,
  VStack,
} from "@chakra-ui/react";
import type { UseServicesManagementReturn } from "../../hooks/useServicesManagement";

export type ServiceCreateFormProps = UseServicesManagementReturn;

export default function ServiceCreateForm(sm: ServiceCreateFormProps) {
  return (
    <Card bg={sm.cardBg} borderColor={sm.cardBorder} borderWidth="1px" boxShadow="none">
      <CardHeader>
        <Heading size="md" color="gray.700" userSelect="none" cursor="default">
          Create New Service
        </Heading>
      </CardHeader>
      <CardBody>
        <form onSubmit={sm.handleSubmit}>
          <VStack spacing={6} align="stretch">
            <FormControl isRequired>
              <FormLabel fontWeight="semibold">
                Service Name{" "}
              </FormLabel>
              <Input
                value={sm.formData.name || ""}
                onChange={(e) => sm.handleInputChange("name", e.target.value)}
                placeholder="Enter service name e.g. asr-conformer-gpu"
                bg="white"
              />
              <Text fontSize="xs" color="gray.500" mt={1}>
                Enter service name e.g. asr-conformer-gpu. Service ID will be auto-generated based on this.
              </Text>
            </FormControl>

            <FormControl isRequired>
              <FormLabel fontWeight="semibold">
                Service Description{" "}
              </FormLabel>
              <Textarea
                value={sm.formData.serviceDescription || ""}
                onChange={(e) => sm.handleInputChange("serviceDescription", e.target.value)}
                placeholder="Provide a brief description of what this service does"
                bg="white"
                rows={4}
              />
            </FormControl>

            <FormControl isRequired>
              <FormLabel fontWeight="semibold">
                Endpoint{" "}
              </FormLabel>
              <Input
                value={sm.formData.endpoint || ""}
                onChange={(e) => sm.handleInputChange("endpoint", e.target.value)}
                placeholder="Enter endpoint URL, e.g. http://localhost:8088"
                bg="white"
              />
              <Text fontSize="xs" color="gray.500" mt={1}>
                Enter the full HTTP endpoint where this service is hosted.
              </Text>
            </FormControl>

            <FormControl isRequired>
              <FormLabel fontWeight="semibold">
                Model Name{" "}
              </FormLabel>
              <Select
                value={sm.formData.modelId || ""}
                onChange={(e) => sm.handleModelNameChange(e.target.value)}
                placeholder={sm.isLoadingModels ? "Loading models..." : "Select the model to be associated with this service"}
                bg="white"
                isDisabled={sm.isLoadingModels}
              >
                {sm.modelsForDropdown.map((model) => (
                  <option key={model.modelId || model.model_id} value={model.modelId || model.model_id}>
                    {model.name || model.modelId || model.model_id}
                  </option>
                ))}
              </Select>
              <Text fontSize="xs" color="gray.500" mt={1}>
                Select the model to be associated with this service.
              </Text>
            </FormControl>

            <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
              <FormControl isRequired>
                <FormLabel fontWeight="semibold">Model ID</FormLabel>
                <Input
                  value={sm.formData.modelId || ""}
                  bg={sm.isCreateFormModelSelected ? "gray.50" : "white"}
                  isReadOnly
                  placeholder="Select a model above"
                />
              </FormControl>

              <FormControl isRequired>
                <FormLabel fontWeight="semibold">Model Task Type</FormLabel>
                <Input
                  value={sm.formData.task_type || ""}
                  placeholder="Select a model above"
                  bg={sm.isCreateFormModelSelected ? "gray.50" : "white"}
                  isReadOnly
                />
              </FormControl>
            </SimpleGrid>

            <FormControl>
              <FormLabel fontWeight="semibold">
                Model Submission Date{" "}
              </FormLabel>
              <Input
                type="date"
                value={(sm.formData.modelSubmissionDate as string) || ""}
                placeholder="Select a model above"
                bg={sm.isCreateFormModelSelected ? "gray.50" : "white"}
                isReadOnly
              />
            </FormControl>

            <HStack justify="flex-end" spacing={4} pt={4}>
              <Button
                type="button"
                variant="outline"
                onClick={sm.resetCreateForm}
              >
                Reset
              </Button>
              <Button
                type="submit"
                colorScheme="blue"
                isLoading={sm.isSubmitting}
                loadingText="Creating..."
                isDisabled={!sm.canCreateService || sm.isSubmitting}
              >
                Create Service
              </Button>
            </HStack>
          </VStack>
        </form>
      </CardBody>
    </Card>
  );
}
