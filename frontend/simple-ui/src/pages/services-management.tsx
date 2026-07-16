// Route shell for /services-management — renders the ServicesManagement feature.
import Head from "next/head";
import React from "react";
import ContentLayout from "../components/common/ContentLayout";
import ServicesManagement from "../components/services-management/ServicesManagement";

const ServicesManagementPage: React.FC = () => {
  return (
    <>
      <Head>
        <title>Services Management - AI4I Platform</title>
        <meta name="description" content="Manage and configure services" />
      </Head>

      <ContentLayout>
        <ServicesManagement />
      </ContentLayout>
    </>
  );
};

export default ServicesManagementPage;
