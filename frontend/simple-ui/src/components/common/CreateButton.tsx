import { AddIcon } from "@chakra-ui/icons";
import { Button, type ButtonProps } from "@chakra-ui/react";
import React from "react";

/**
 * Primary Create / Add / New control for Manage pages.
 * Colour, height, radius, and hover come from the shared Button theme.
 */
export default function CreateButton({
  children,
  size = "sm",
  ...rest
}: Omit<ButtonProps, "leftIcon" | "colorScheme" | "variant">) {
  return (
    <Button size={size} leftIcon={<AddIcon />} {...rest}>
      {children}
    </Button>
  );
}
