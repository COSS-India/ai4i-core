import {
  Box,
  Center,
  Drawer,
  DrawerBody,
  DrawerCloseButton,
  DrawerContent,
  DrawerHeader,
  DrawerOverlay,
  HStack,
  Spinner,
  Table,
  Tbody,
  Td,
  Text,
  Thead,
  Tr,
  VStack,
} from "@chakra-ui/react";
import React from "react";
import { METERING } from "../../config/meteringConstants";
import type { ApplicationUsageDetail } from "../../types/applicationUsage";
import { formatSpendMoney } from "../../utils/usageSpendHelpers";
import {
  AllocatedPctPill,
  ApiKeyStatusBadge,
  ApplicationRemainingCell,
  ApplicationSpendCell,
} from "./ApplicationUsageCells";
import { BudgetCell, TenantAvatar } from "./UsageSpendCells";
import { ThWithTip } from "../common/InfoTip";

interface ApplicationUsageDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  detail: ApplicationUsageDetail | null;
  isLoading: boolean;
  currency?: string;
}

const CARD_BG = "#eef3fb";

const ApplicationUsageDrawer: React.FC<ApplicationUsageDrawerProps> = ({
  isOpen,
  onClose,
  detail,
  isLoading,
  currency = "INR",
}) => {
  const copy = METERING.APPLICATION_USAGE;
  const tips = copy.TOOLTIPS;
  const cols = copy.TABLE;

  let body: React.ReactNode = null;
  if (isLoading && !detail) {
    body = (
      <Center py={12}>
        <Spinner color="blue.500" />
      </Center>
    );
  } else if (detail) {
    const limit = detail.allocatedBudget.amount;
    const spent = detail.spendBudget.amount;
    const remaining = detail.remainingBudget.amount;
    const hasBudget = limit > 0;
    const pctUsed = hasBudget ? (spent / limit) * 100 : 0;

    body = (
      <VStack align="stretch" spacing={5}>
        <HStack spacing={3} pt={1}>
          <TenantAvatar name={detail.applicationName} size="md" />
          <Text fontSize="16px" fontWeight="bold" color="gray.800">
            {detail.applicationName}
          </Text>
        </HStack>

        <Box>
          <Text fontSize="11.5px" letterSpacing="0.05em" color="gray.500" fontWeight="bold" mb="10px">
            BUDGET
          </Text>
          <Box
            bg={CARD_BG}
            borderRadius="12px"
            borderWidth="1px"
            borderColor="gray.200"
            p="18px 20px"
            opacity={isLoading ? 0.55 : 1}
          >
            {hasBudget ? (
              <BudgetCell
                limit={limit}
                spent={spent}
                remaining={remaining}
                percentageUsed={pctUsed}
                currency={currency}
              />
            ) : (
              <Text fontSize="13.5px" color="gray.500" fontStyle="italic">
                {copy.DRAWER_NO_BUDGET}
              </Text>
            )}
          </Box>
        </Box>

        <Box position="relative" opacity={isLoading ? 0.55 : 1}>
          {isLoading ? (
            <Center position="absolute" inset={0} zIndex={1}>
              <Spinner color="blue.500" size="sm" />
            </Center>
          ) : null}
          <Text fontSize="11.5px" letterSpacing="0.05em" color="gray.500" fontWeight="bold" mb="10px">
            {copy.DRAWER_SPEND_BY_API_KEY}
          </Text>
          {detail.apiKeys.length === 0 ? (
            <Text fontSize="13.5px" color="gray.500" fontStyle="italic" py={3}>
              {copy.DRAWER_NO_KEYS}
            </Text>
          ) : (
            <Box overflowX="auto" borderWidth="1px" borderColor="gray.300" borderRadius="10px">
              <Table size="sm" variant="simple">
                <Thead bg="#FAFBFD">
                  <Tr>
                    <ThWithTip fontSize="10.5px" letterSpacing="0.03em" color="gray.500">
                      {cols.API_KEY}
                    </ThWithTip>
                    <ThWithTip
                      fontSize="10.5px"
                      letterSpacing="0.03em"
                      color="gray.500"
                      message={tips.API_KEY_ALLOCATED}
                    >
                      {cols.ALLOCATED_SHORT}
                    </ThWithTip>
                    <ThWithTip
                      fontSize="10.5px"
                      letterSpacing="0.03em"
                      color="gray.500"
                      message={tips.API_KEY_SPEND}
                    >
                      {cols.SPEND_SHORT}
                    </ThWithTip>
                    <ThWithTip
                      fontSize="10.5px"
                      letterSpacing="0.03em"
                      color="gray.500"
                      message={tips.API_KEY_REMAINING}
                    >
                      {cols.REMAINING_SHORT}
                    </ThWithTip>
                  </Tr>
                </Thead>
                <Tbody>
                  {detail.apiKeys.map((key) => {
                    const keyLimit = key.allocatedBudget.amount;
                    const keySpent = key.spendBudget.amount;
                    const keyRemaining = key.remainingBudget.amount;
                    const keyHasBudget = keyLimit > 0;
                    const keyPct = keyHasBudget ? (keySpent / keyLimit) * 100 : 0;
                    return (
                      <Tr key={key.keyId}>
                        <Td verticalAlign="top">
                          <Text fontWeight="bold" fontSize="13.5px" color="gray.800">
                            {key.keyName}
                          </Text>
                          <Text fontFamily="mono" fontSize="11px" color="gray.500" mt="2px">
                            •••• {key.maskedKey}
                          </Text>
                          <ApiKeyStatusBadge isActive={key.isActive} />
                        </Td>
                        <Td verticalAlign="top">
                          {keyHasBudget ? (
                            <Text fontSize="13px" fontWeight="bold" color="gray.800">
                              {formatSpendMoney(keyLimit, currency)}
                              <AllocatedPctPill pct={key.allocatedBudget.percentage} />
                            </Text>
                          ) : (
                            <Text fontSize="12px" color="gray.500" fontStyle="italic">
                              {cols.NO_BUDGET}
                            </Text>
                          )}
                        </Td>
                        <Td verticalAlign="top">
                          <ApplicationSpendCell
                            spent={keySpent}
                            remaining={keyRemaining}
                            pctUsed={keyPct}
                            currency={currency}
                            hasBudget={keyHasBudget}
                            noBudgetLabel={cols.NO_BUDGET}
                          />
                        </Td>
                        <Td verticalAlign="top">
                          <ApplicationRemainingCell
                            remaining={keyRemaining}
                            pctOfAllocation={key.remainingBudget.percentage}
                            currency={currency}
                            hasBudget={keyHasBudget}
                            ofAllocationLabel="remaining"
                          />
                        </Td>
                      </Tr>
                    );
                  })}
                  <Tr bg="#FAFBFD">
                    <Td fontWeight="extrabold" fontSize="13px" color="gray.800">
                      Total
                    </Td>
                    <Td fontWeight="extrabold" fontSize="13px" color="gray.800">
                      {formatSpendMoney(detail.totals.allocatedBudget, currency)}
                    </Td>
                    <Td fontWeight="extrabold" fontSize="13px" color="gray.800">
                      {formatSpendMoney(detail.totals.spendBudget, currency)}
                    </Td>
                    <Td fontWeight="extrabold" fontSize="13px" color="gray.800">
                      {formatSpendMoney(detail.totals.remainingBudget, currency)}
                    </Td>
                  </Tr>
                </Tbody>
              </Table>
            </Box>
          )}
        </Box>
      </VStack>
    );
  }

  return (
    <Drawer isOpen={isOpen} placement="right" onClose={onClose} size="md">
      <DrawerOverlay bg="rgba(15,23,42,0.35)" />
      <DrawerContent maxW="460px">
        <DrawerCloseButton top={4} right={4} />
        <DrawerHeader fontSize="19px" fontWeight="extrabold" pb={2} pt={6}>
          {copy.DRAWER_TITLE}
        </DrawerHeader>
        <DrawerBody pb={10}>{body}</DrawerBody>
      </DrawerContent>
    </Drawer>
  );
};

export default ApplicationUsageDrawer;
