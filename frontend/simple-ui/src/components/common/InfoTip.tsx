import { Box, HStack, Icon, Text, Th, Tooltip } from "@chakra-ui/react";
import React from "react";
import { FiInfo } from "react-icons/fi";

interface InfoTipProps {
  /** Hover text shown on the circled-i icon. */
  message: string;
}

/** Circled-i hover tip. */
const InfoTip: React.FC<InfoTipProps> = ({ message }) => (
  <Tooltip label={message} hasArrow placement="top" openDelay={200} maxW="260px">
    <Box as="span" display="inline-flex" cursor="help" color="gray.400" lineHeight={1}>
      <Icon as={FiInfo} boxSize={3.5} aria-label={message} />
    </Box>
  </Tooltip>
);

type ThWithTipProps = React.ComponentProps<typeof Th> & {
  /** Hover text. Omit to hide the icon. */
  message?: string;
};

/** Table header cell with an optional circled-i tip. Spreads remaining props onto `<Th>`. */
export const ThWithTip: React.FC<ThWithTipProps> = ({
  message,
  isNumeric,
  children,
  ...thProps
}) => (
  <Th
    fontSize="xs"
    textTransform="uppercase"
    color="gray.500"
    isNumeric={isNumeric}
    {...thProps}
  >
    <HStack spacing={1} justify={isNumeric ? "flex-end" : "flex-start"}>
      {typeof children === "string" ? (
        <Text as="span" color="inherit">{children}</Text>
      ) : (
        children
      )}
      {message ? <InfoTip message={message} /> : null}
    </HStack>
  </Th>
);

export default InfoTip;
