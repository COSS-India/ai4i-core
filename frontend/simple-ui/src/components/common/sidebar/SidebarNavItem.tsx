// Single sidebar navigation button (top-level or nested service item)

import { Button, Heading, Icon, Text } from "@chakra-ui/react";
import React from "react";
import { TABS } from "../../../config/constants";
import type { NavItem } from "./navConfig";
import { getNavItemColor } from "./navConfig";

export type SidebarNavItemVariant = "top" | "service";

export interface SidebarNavItemProps {
  item: NavItem;
  isActive: boolean;
  isExpanded: boolean;
  variant: SidebarNavItemVariant;
  hoverBgColor: string;
  onClick: (e: React.MouseEvent, path: string, requiresAuth: boolean) => void;
}

const SidebarNavItem: React.FC<SidebarNavItemProps> = ({
  item,
  isActive,
  isExpanded,
  variant,
  hoverBgColor,
  onClick,
}) => {
  const requiresAuth = item.requiresAuth ?? false;
  const iconColor =
    item.id === TABS.home ? "black" : getNavItemColor(item.id, 600);

  if (variant === "service") {
    return (
      <Button
        variant="ghost"
        size="sm"
        h="2.5rem"
        minH="2.5rem"
        w="full"
        justifyContent="flex-start"
        leftIcon={<Icon as={item.icon} boxSize={4} color={iconColor} />}
        bg={isActive ? "gray.200" : "transparent"}
        color={isActive ? "gray.800" : "gray.700"}
        boxShadow={isActive ? "sm" : "none"}
        borderLeft={isActive ? "3px solid" : "3px solid transparent"}
        borderLeftColor={isActive ? iconColor : "transparent"}
        borderRadius="md"
        onClick={(e) => onClick(e, item.path, requiresAuth)}
        _hover={{
          bg: isActive ? "gray.200" : hoverBgColor,
          transform: "translateY(-1px)",
          borderLeftColor: iconColor,
          borderLeft: "3px solid",
        }}
        transition="all 0.2s"
        px={1}
      >
        <Text fontSize="sm" color="gray.800" fontWeight="medium" whiteSpace="pre-line">
          {item.label}
        </Text>
      </Button>
    );
  }

  return (
    <Button
      variant="ghost"
      size="sm"
      h="3rem"
      minH="3rem"
      w="full"
      justifyContent={isExpanded ? "flex-start" : "center"}
      leftIcon={
        isExpanded ? <Icon as={item.icon} boxSize={5} color={iconColor} /> : undefined
      }
      bg={isActive ? "gray.200" : "transparent"}
      color={isActive ? "gray.800" : "gray.700"}
      boxShadow={isActive ? "sm" : "none"}
      onClick={(e) => onClick(e, item.path, requiresAuth)}
      _hover={{
        bg: isActive ? "gray.200" : hoverBgColor,
        transform: "translateY(-1px)",
      }}
      transition="all 0.2s"
      px={isExpanded ? 3 : 0}
    >
      {isExpanded ? (
        <Heading size="sm" color="gray.800" fontWeight="medium" whiteSpace="pre-line">
          {item.label}
        </Heading>
      ) : (
        <Icon as={item.icon} boxSize={6} color={iconColor} />
      )}
    </Button>
  );
};

export default SidebarNavItem;
