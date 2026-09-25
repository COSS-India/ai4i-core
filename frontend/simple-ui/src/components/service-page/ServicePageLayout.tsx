// Standard two-column layout shell for AI service try-it pages

import React from "react";
import { Box, Grid, VStack } from "@chakra-ui/react";
import Head from "next/head";
import ContentLayout from "../common/ContentLayout";
import ManagementPageHeader from "../common/ManagementPageHeader";
import {
  getServiceDescription,
  getServiceTitle,
  type ServiceId,
} from "../../config/serviceMetadata";
import type { ServicePageLayoutProps } from "../../types/servicePage";
import { getPlatformName } from "../../config/runtimeConfig";

const ServicePageLayout: React.FC<ServicePageLayoutProps> = ({
  serviceId,
  pageTitle,
  pageDescription,
  headTitle,
  headDescription,
  headerExtra,
  banner,
  requestPanel,
  responsePanel,
  maxWidth = "1200px",
}) => {
  const title = pageTitle ?? getServiceTitle(serviceId as ServiceId);
  const description = pageDescription ?? getServiceDescription(serviceId as ServiceId);
  const metaTitle = headTitle ?? `${title} | ${getPlatformName()}`;

  return (
    <>
      <Head>
        <title>{metaTitle}</title>
        {headDescription && <meta name="description" content={headDescription} />}
      </Head>

      <ContentLayout>
        <VStack spacing={6} w="full">
          <Box w="full" maxW={maxWidth} mx="auto">
            <ManagementPageHeader
              title={title}
              description={description}
              actions={headerExtra}
            />
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
