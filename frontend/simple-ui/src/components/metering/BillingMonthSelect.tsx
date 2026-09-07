import { Select } from "@chakra-ui/react";
import React from "react";
import { METERING } from "../../config/meteringConstants";
import { billingPeriodOptions, formatBillingPeriodDisplay } from "../../utils/usageSpendHelpers";

interface BillingMonthSelectProps {
  value: string;
  onChange: (value: string) => void;
}

const BillingMonthSelect: React.FC<BillingMonthSelectProps> = ({ value, onChange }) => (
  <Select
    size="sm"
    value={value}
    onChange={(e) => onChange(e.target.value)}
    w={{ base: "full", sm: "auto" }}
    minW={{ sm: "200px" }}
    maxW={{ sm: "240px" }}
    borderRadius="full"
    bg="white"
    fontSize="13px"
    fontWeight="medium"
    borderColor="gray.300"
  >
    {billingPeriodOptions().map((opt) => (
      <option key={opt.value} value={opt.value}>
        {METERING.USAGE_SPEND.MONTH_FILTER_PREFIX} · {formatBillingPeriodDisplay(opt.value)}
      </option>
    ))}
  </Select>
);

export default BillingMonthSelect;
