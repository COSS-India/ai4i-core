import type { ReactNode } from "react";
import {
  IconButton,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
  Tooltip,
} from "@chakra-ui/react";
import { ChevronDownIcon } from "@chakra-ui/icons";

export interface RowActionMenuItem {
  key: string;
  label: string;
  onSelect: () => void;
  color: string;
  hoverBg: string;
  icon: ReactNode;
  isDisabled?: boolean;
}

interface TenantOverflowActionMenuProps {
  items: RowActionMenuItem[];
  stopRowClick: (e: React.MouseEvent) => void;
  menuAriaLabel: string;
}

export default function TenantOverflowActionMenu({
  items,
  stopRowClick,
  menuAriaLabel,
}: TenantOverflowActionMenuProps) {
  return (
    <Menu>
      <MenuButton
        as={IconButton}
        aria-label={menuAriaLabel}
        icon={<ChevronDownIcon />}
        size="sm"
        variant="ghost"
        colorScheme="gray"
        _hover={{ bg: "gray.100" }}
        onClick={stopRowClick}
      />
      <MenuList minW="auto" w="auto" py={1}>
        {items.map((item) => (
          <Tooltip key={item.key} label={item.label} placement="left" hasArrow openDelay={300}>
            <MenuItem
              aria-label={item.label}
              color={item.color}
              _hover={{ bg: item.hoverBg }}
              isDisabled={item.isDisabled}
              px={2}
              py={2}
              minH="8"
              w="auto"
              onClick={(e) => {
                stopRowClick(e);
                item.onSelect();
              }}
            >
              {item.icon}
            </MenuItem>
          </Tooltip>
        ))}
      </MenuList>
    </Menu>
  );
}
