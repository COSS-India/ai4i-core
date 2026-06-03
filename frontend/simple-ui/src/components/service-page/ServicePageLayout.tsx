// Standard two-column layout shell for AI service try-it pages

import React from "react";
import { Box, Flex, Grid, Heading, Text, VStack } from "@chakra-ui/react";
import Head from "next/head";
import ContentLayout from "../common/ContentLayout";
import {
  getServiceDescription,
  getServiceTitle,
  type ServiceId,
} from "../../config/serviceMetadata";
import type { ServicePageLayoutProps } from "../../types/servicePage";

const ServicePageLayout: React.FC<ServicePageLayoutProps> = ({
  serviceId,
  pageTitle,
  pageDescription,
  headTitle,
  headDescription,
  headingSize = "xl",
  headerExtra,
  banner,
  requestPanel,
  responsePanel,
  maxWidth = "1200px",
}) => {
  const title = pageTitle ?? getServiceTitle(serviceId as ServiceId);
  const description = pageDescription ?? getServiceDescription(serviceId as ServiceId);
  const metaTitle = headTitle ?? `${title} | AI4Inclusion Console`;
  const descFontSize = headingSize === "lg" ? "sm" : "lg";

  return (
    <>
      <Head>
        <title>{metaTitle}</title>
        {headDescription && <meta name="description" content={headDescription} />}
      </Head>

      <ContentLayout>
        <VStack spacing={8} w="full">
          <Box w="full" maxW={maxWidth} mx="auto">
            <Flex
              direction="row"
              justify={headerExtra ? "space-between" : "center"}
              align="center"
              mb={headerExtra ? 4 : 0}
              w="full"
            >
              <Box flex={1} textAlign="center">
                <Heading
                  size={headingSize}
                  color="gray.800"
                  mb={headingSize === "lg" ? 1 : 2}
                  userSelect="none"
                  cursor="default"
                  tabIndex={-1}
                >
                  {title}
                </Heading>
                <Text
                  color="gray.600"
                  fontSize={descFontSize}
                  userSelect="none"
                  cursor="default"
                >
                  {description}
                </Text>
              </Box>
              {headerExtra}
            </Flex>
          </Box>

          {banner}

          <Grid
            templateColumns={{ base: "1fr", lg: "1fr 1fr" }}
            gap={8}
            w="full"
            maxW={maxWidth}
            mx="auto"
          >
            {requestPanel}
            {responsePanel}
          </Grid>
        </VStack>
      </ContentLayout>
    </>
  );
};

export default ServicePageLayout;
