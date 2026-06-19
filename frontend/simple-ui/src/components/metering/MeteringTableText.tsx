import { Text, TextProps } from "@chakra-ui/react";
import React from "react";

interface MeteringTableTextProps extends TextProps {
  children: string;
  /** Show full value on hover when truncated. Defaults to children. */
  title?: string;
}

/** Single-line table cell text with ellipsis and native tooltip. */
const MeteringTableText: React.FC<MeteringTableTextProps> = ({
  children,
  title,
  fontWeight = "medium",
  fontSize = "sm",
  color = "gray.800",
  maxW = "280px",
  ...rest
}) => (
  <Text
    fontWeight={fontWeight}
    fontSize={fontSize}
    color={color}
    maxW={maxW}
    noOfLines={1}
    isTruncated
    title={title ?? children}
    lineHeight="short"
    {...rest}
  >
    {children}
  </Text>
);

export default MeteringTableText;
