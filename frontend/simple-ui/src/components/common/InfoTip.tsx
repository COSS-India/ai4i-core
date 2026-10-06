import { Box, Icon, Tooltip } from "@chakra-ui/react";
import React from "react";
import { FiInfo } from "react-icons/fi";

interface InfoTipProps {
  /** Hover text shown on the circled-i icon. */
  message: string;
}

/** Circled-i hover tip. Prefer {@link FieldLabel} when pairing with a text label. */
const InfoTip: React.FC<InfoTipProps> = ({ message }) => (
  <Tooltip label={message} hasArrow placement="top" openDelay={200} maxW="260px">
    <Box as="span" display="inline-flex" cursor="help" color="ink.500" lineHeight={1}>
      <Icon as={FiInfo} boxSize={3.5} aria-label={message} />
    </Box>
  </Tooltip>
);

export default InfoTip;
