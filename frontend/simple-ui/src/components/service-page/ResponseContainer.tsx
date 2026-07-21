// Right-panel response area for AI service pages

import React from "react";
import { Box, Button, GridItem, Progress, Text, VStack } from "@chakra-ui/react";
import type { ResponseContainerProps } from "../../types/servicePage";
import { FeedbackWidget } from "../feedback";
import ResponseActions from "./response/ResponseActions";
import ResponseMetadata from "./response/ResponseMetadata";
import ResultDisplay from "./response/ResultDisplay";

const ResponseContainer: React.FC<ResponseContainerProps> = ({
  fetching = false,
  fetchingLabel = "Processing...",
  error,
  fetched = false,
  hasResult = false,
  resultTitle,
  resultContent,
  result,
  metadata = [],
  actions = [],
  onClear,
  clearLabel = "Clear Results",
  children,
  feedback,
}) => {
  const showResult = hasResult || (fetched && (!!resultContent || !!result));

  return (
    <GridItem pt={0} mt={0} alignSelf="flex-start">
      <VStack spacing={6} align="stretch" pt={0} mt={0}>
        {fetching && (
          <Box>
            <Text mb={2} fontSize="sm" color="gray.600">
              {fetchingLabel}
            </Text>
            <Progress size="xs" isIndeterminate colorScheme="orange" />
          </Box>
        )}

        {error && (
          <Box p={4} bg="red.50" borderRadius="md" border="1px" borderColor="red.200">
            <Text color="red.600" fontSize="sm">
              {error}
            </Text>
          </Box>
        )}

        {showResult && (
          <>
            {result ?? (
              resultContent && (
                <ResultDisplay title={resultTitle} content={resultContent} />
              )
            )}
            {metadata.length > 0 && <ResponseMetadata items={metadata} />}
            {actions.length > 0 && <ResponseActions actions={actions} />}
            {feedback && (
              <FeedbackWidget
                requestId={feedback.requestId}
                modelTaskType={feedback.modelTaskType}
                modelProvider={feedback.modelProvider}
                modelVersion={feedback.modelVersion}
                modelId={feedback.modelId}
                languageInfo={feedback.languageInfo}
                originalOutput={feedback.originalOutput}
                disabled={fetching}
              />
            )}
            {children}
            {onClear && (
              <Box textAlign="center">
                <Button size="sm" variant="outline" onClick={onClear}>
                  {clearLabel}
                </Button>
              </Box>
            )}
          </>
        )}
      </VStack>
    </GridItem>
  );
};

export default ResponseContainer;
