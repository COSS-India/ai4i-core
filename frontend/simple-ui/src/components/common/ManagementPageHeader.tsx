import { Box, Flex, Heading, Text } from "@chakra-ui/react";
import { useRouter } from "next/router";
import React from "react";
import { useAuth } from "../../hooks/useAuth";
import { getHomePath } from "../../utils/navigation";
import PageBreadcrumb, {
  getPageBreadcrumbs,
  type Crumb,
} from "./PageBreadcrumb";

interface ManagementPageHeaderProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  /** Override auto trail, or `false` to hide. */
  crumbs?: Crumb[] | false;
}

const ManagementPageHeader: React.FC<ManagementPageHeaderProps> = ({
  title,
  description,
  actions,
  crumbs,
}) => {
  const router = useRouter();
  const { user } = useAuth();
  const items =
    crumbs === false
      ? null
      : crumbs ?? getPageBreadcrumbs(router.pathname, title, getHomePath(user?.roles));

  return (
    <Box
      w="full"
      mb={4}
      pb={4}
      borderBottom="1px"
      borderColor="ink.200"
    >
      {items ? <PageBreadcrumb items={items} /> : null}
      <Flex
        align={{ base: "flex-start", md: "center" }}
        justify="space-between"
        gap={4}
        direction={{ base: "column", md: "row" }}
      >
        <Box textAlign="left" minW={0}>
          <Heading
            as="h1"
            size="lg"
            color="ink.800"
            mb={description ? 1 : 0}
            userSelect="none"
            cursor="default"
            tabIndex={-1}
          >
            {title}
          </Heading>
          {description ? (
            <Text color="ink.600" fontSize="sm" fontWeight="500" maxW="46rem" lineHeight="1.5">
              {description}
            </Text>
          ) : null}
        </Box>
        {actions}
      </Flex>
    </Box>
  );
};

export default ManagementPageHeader;
