import {
  Box,
  Button,
  Checkbox,
  Menu,
  MenuButton,
  MenuDivider,
  MenuItem,
  MenuList,
  Portal,
  Text,
  Tooltip,
} from "@chakra-ui/react";
import { ChevronDownIcon, SettingsIcon } from "@chakra-ui/icons";
import React from "react";

export type AdminListColumnDef = {
  id: string;
  label: string;
  mandatory: boolean;
};

type AdminListColumnPickerProps<T extends AdminListColumnDef> = Readonly<{
  columns: readonly T[];
  visibleIds: readonly string[];
  helper: string;
  mandatoryHint: string;
  canToggleOff: (
    current: readonly string[],
    id: string,
    catalogue: readonly T[],
  ) => boolean;
  toggle: (
    current: readonly string[],
    id: string,
    catalogue: readonly T[],
  ) => string[];
  onChange: (next: string[]) => void;
  onReset: () => void;
}>;

/**
 * Shared Columns menu for admin list tables (Services, Models, …).
 * Domain pickers supply catalogue helpers and copy only.
 */
function AdminListColumnPicker<T extends AdminListColumnDef>({
  columns,
  visibleIds,
  helper,
  mandatoryHint,
  canToggleOff,
  toggle,
  onChange,
  onReset,
}: AdminListColumnPickerProps<T>) {
  return (
    <Menu closeOnSelect={false}>
      <Tooltip label={helper} placement="top" hasArrow>
        <Box as="span" display="inline-block">
          <MenuButton
            as={Button}
            size="sm"
            variant="outline"
            leftIcon={<SettingsIcon />}
            rightIcon={<ChevronDownIcon />}
            aria-label="Choose columns"
          >
            Columns
          </MenuButton>
        </Box>
      </Tooltip>
      <Portal>
        <MenuList
          maxH="360px"
          overflowY="auto"
          minW="260px"
          py={2}
          zIndex="popover"
        >
          <Text px={3} pb={1} fontSize="xs" color="ink.500" fontWeight="medium">
            {helper}
          </Text>
          <Text px={3} pb={2} fontSize="xs" color="ink.400">
            {mandatoryHint}
          </Text>
          {columns.map((column) => {
            const checked = visibleIds.includes(column.id);
            const canTurnOff = canToggleOff(visibleIds, column.id, columns);
            const locked =
              column.mandatory || (checked && canTurnOff === false);
            return (
              <MenuItem
                as="div"
                key={column.id}
                closeOnSelect={false}
                isDisabled={locked}
                onClick={() => {
                  if (locked) return;
                  onChange(toggle(visibleIds, column.id, columns));
                }}
                py={1.5}
                cursor={locked ? "not-allowed" : "pointer"}
              >
                <Checkbox
                  isChecked={checked}
                  isDisabled={locked}
                  pointerEvents="none"
                  colorScheme="blue"
                  mr={2}
                >
                  <Text as="span" fontSize="sm">
                    {column.label}
                    {column.mandatory ? (
                      <Text as="span" color="ink.400" ml={1}>
                        (required)
                      </Text>
                    ) : null}
                  </Text>
                </Checkbox>
              </MenuItem>
            );
          })}
          <MenuDivider />
          <MenuItem onClick={onReset} fontSize="sm" color="blue.600">
            Reset to default
          </MenuItem>
        </MenuList>
      </Portal>
    </Menu>
  );
}

export default AdminListColumnPicker;
