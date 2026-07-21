import React from "react";
import { IconButton, Tooltip } from "@chakra-ui/react";
import { FaRegThumbsDown, FaRegThumbsUp, FaThumbsDown, FaThumbsUp } from "react-icons/fa";

export interface ThumbsControlProps {
  rating: "POSITIVE" | "NEGATIVE" | null;
  disabled?: boolean;
  accentColor?: string;
  colorScheme?: string;
  rateHelpfulLabel: string;
  rateNotHelpfulLabel: string;
  onPositive: () => void;
  onNegative: () => void;
}

const ThumbsControl: React.FC<ThumbsControlProps> = ({
  rating,
  disabled = false,
  accentColor,
  colorScheme = "orange",
  rateHelpfulLabel,
  rateNotHelpfulLabel,
  onPositive,
  onNegative,
}) => {
  const activeColor = accentColor || `${colorScheme}.500`;
  const activeBg = accentColor ? undefined : `${colorScheme}.50`;

  return (
    <>
      <Tooltip label={rateHelpfulLabel} hasArrow>
        <IconButton
          aria-label={rateHelpfulLabel}
          icon={rating === "POSITIVE" ? <FaThumbsUp /> : <FaRegThumbsUp />}
          size="sm"
          variant="outline"
          isDisabled={disabled}
          onClick={onPositive}
          borderColor={rating === "POSITIVE" ? activeColor : "gray.200"}
          color={rating === "POSITIVE" ? activeColor : "gray.600"}
          bg={rating === "POSITIVE" ? activeBg || "gray.50" : "white"}
          _hover={{ borderColor: activeColor, color: activeColor }}
          borderRadius="md"
        />
      </Tooltip>
      <Tooltip label={rateNotHelpfulLabel} hasArrow>
        <IconButton
          aria-label={rateNotHelpfulLabel}
          icon={rating === "NEGATIVE" ? <FaThumbsDown /> : <FaRegThumbsDown />}
          size="sm"
          variant="outline"
          isDisabled={disabled}
          onClick={onNegative}
          borderColor={rating === "NEGATIVE" ? activeColor : "gray.200"}
          color={rating === "NEGATIVE" ? activeColor : "gray.600"}
          bg={rating === "NEGATIVE" ? activeBg || "gray.50" : "white"}
          _hover={{ borderColor: activeColor, color: activeColor }}
          borderRadius="md"
        />
      </Tooltip>
    </>
  );
};

export default ThumbsControl;
