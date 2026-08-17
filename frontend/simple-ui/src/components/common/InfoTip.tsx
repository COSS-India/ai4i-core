import { Box, HStack, Icon, Text, Th, Tooltip } from "@chakra-ui/react";
import React from "react";
import { FiInfo } from "react-icons/fi";

interface InfoTipProps {
  /** Hover text. Omit to hide the icon (header-only). */
  message?: string;
  /** When set, render as a table `<Th>` with this title. */
  header?: string;
  isNumeric?: boolean;
  minW?: string | number;
  w?: string | number;
  sx?: Record<string, string | number>;
  onClick?: () => void;
  cursor?: string;
  userSelect?: "none" | "auto";
  children?: React.ReactNode;
}

function InfoIcon({ message }: { message: string }) {
  return (
    <Tooltip label={message} hasArrow placement="top" openDelay={200} maxW="260px">
      <Box as="span" display="inline-flex" cursor="help" color="gray.400" lineHeight={1}>
        <Icon as={FiInfo} boxSize={3.5} aria-label={message} />
      </Box>
    </Tooltip>
  );
}

/** Circled-i hover tip. Pass `message` for the icon; pass `header` to use as a table column. */
const InfoTip: React.FC<InfoTipProps> = ({
  message,
  header,
  isNumeric,
  minW,
  w,
  sx,
  onClick,
  cursor,
  userSelect,
  children,
}) => {
  const icon = message ? <InfoIcon message={message} /> : null;

  if (header == null) return icon;

  return (
    <Th
      fontSize="xs"
      textTransform="uppercase"
      color="gray.500"
      isNumeric={isNumeric}
      minW={minW}
      w={w}
      sx={sx}
      onClick={onClick}
      cursor={cursor}
      userSelect={userSelect}
    >
      <HStack spacing={1} justify={isNumeric ? "flex-end" : "flex-start"}>
        {children ?? <Text as="span">{header}</Text>}
        {icon}
      </HStack>
    </Th>
  );
};

export default InfoTip;
