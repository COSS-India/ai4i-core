import {
  Badge,
  Box,
  Card,
  CardBody,
  CardHeader,
  Center,
  Divider,
  Grid,
  Heading,
  HStack,
  Icon,
  SimpleGrid,
  StackDivider,
  Text,
  VStack,
} from "@chakra-ui/react";
import React from "react";
import type { IconType } from "react-icons";
import { FiLayers, FiUser } from "react-icons/fi";
import {
  INSTITUTION,
  formatTenantStatusLabel,
  getTenantStatusColorScheme,
} from "../../config/constants";
import type { TenantView } from "../../types/tenant";
import { fmtDate } from "../../utils/valueFormatters";
import InstitutionContactEmail from "./InstitutionContactEmail";

type OverviewCardProps = Readonly<{
  title: string;
  icon: IconType;
  children: React.ReactNode;
}>;

function OverviewCard({ title, icon, children }: OverviewCardProps) {
  return (
    <Card variant="outline" borderRadius="xl" h="full">
      <CardHeader pb={0}>
        <HStack spacing={3}>
          <Center
            boxSize={9}
            borderRadius="md"
            bg="blue.50"
            _dark={{ bg: "whiteAlpha.100" }}
            flexShrink={0}
          >
            <Icon as={icon} boxSize={5} color="blue.500" aria-hidden />
          </Center>
          <Heading as="h3" size="sm" color="ink.800">
            {title}
          </Heading>
        </HStack>
      </CardHeader>
      <Divider borderColor="ink.200" mt={4} mx={5} w="auto" />
      <CardBody pt={2}>{children}</CardBody>
    </Card>
  );
}

/** Label stacked above its value — the contact side of the overview. */
function StackedField({
  label,
  children,
}: Readonly<{ label: string; children: React.ReactNode }>) {
  return (
    <Box minW={0} py={3}>
      <Text fontSize="sm" color="ink.500" mb={1}>
        {label}
      </Text>
      {typeof children === "string" ? (
        <Text fontSize="md" color="ink.800" wordBreak="break-word">
          {children}
        </Text>
      ) : (
        children
      )}
    </Box>
  );
}

/** Label beside its value — the tier & budget side of the overview. */
function InlineField({
  label,
  children,
}: Readonly<{ label: string; children: React.ReactNode }>) {
  return (
    <Grid templateColumns="minmax(0, 2fr) minmax(0, 3fr)" gap={4} py={3} alignItems="center">
      <Text fontSize="sm" color="ink.500">
        {label}
      </Text>
      <Box minW={0}>
        {typeof children === "string" ? (
          <Text fontSize="md" color="ink.800" wordBreak="break-word">
            {children}
          </Text>
        ) : (
          children
        )}
      </Box>
    </Grid>
  );
}

function NotProvided() {
  return (
    <Text fontSize="md" color="ink.400">
      Not provided
    </Text>
  );
}

type InstitutionOverviewProps = Readonly<{
  tenant: TenantView;
  tierLabel: string;
  budgetLabel: string;
  /** Extra content under the Tier & budget fields (rate limit, quotas, warnings). */
  tierExtras?: React.ReactNode;
  /** Full-width content under the two cards (e.g. view-only guidance). */
  footer?: React.ReactNode;
}>;

/** Two-column card layout for an institution overview — adopter and tenant admin. */
export default function InstitutionOverview({
  tenant: t,
  tierLabel,
  budgetLabel,
  tierExtras,
  footer,
}: InstitutionOverviewProps) {
  const hasBudgetPeriod = Boolean(t.budget_effective_from || t.budget_effective_to);
  const rowDivider = <StackDivider borderColor="ink.100" />;
  return (
    <VStack align="stretch" spacing={6} w="full">
      <SimpleGrid columns={{ base: 1, lg: 2 }} spacing={6} w="full" alignItems="stretch">
        <OverviewCard title={`${INSTITUTION} details`} icon={FiUser}>
          <VStack align="stretch" spacing={0} divider={rowDivider}>
            <StackedField label="Contact name">
              {t.contact_name?.trim() ? t.contact_name : <NotProvided />}
            </StackedField>
            <StackedField label="Email address">
              <InstitutionContactEmail email={t.email} pendingEmail={t.pending_email} />
            </StackedField>
            <StackedField label="Phone number">
              {t.phone_number?.trim() ? t.phone_number : <NotProvided />}
            </StackedField>
          </VStack>
        </OverviewCard>

        <OverviewCard title="Tier & budget" icon={FiLayers}>
          <VStack align="stretch" spacing={0} divider={rowDivider}>
            <InlineField label={`${INSTITUTION} ID`}>{String(t.tenant_id)}</InlineField>
            <InlineField label="Status">
              <Badge
                colorScheme={getTenantStatusColorScheme(t.status)}
                borderRadius="full"
                px={2.5}
                py={0.5}
                textTransform="none"
              >
                {formatTenantStatusLabel(t.status)}
              </Badge>
            </InlineField>
            <InlineField label="Tier">{tierLabel}</InlineField>
            <InlineField label="Created on">{fmtDate(t.created_at)}</InlineField>
            <InlineField label="Allocated budget">{budgetLabel}</InlineField>
            {hasBudgetPeriod ? (
              <InlineField label="Budget period">
                {`${fmtDate(t.budget_effective_from)} – ${fmtDate(t.budget_effective_to)}`}
              </InlineField>
            ) : null}
            {tierExtras ? <Box pt={3}>{tierExtras}</Box> : null}
          </VStack>
        </OverviewCard>
      </SimpleGrid>
      {footer}
    </VStack>
  );
}
