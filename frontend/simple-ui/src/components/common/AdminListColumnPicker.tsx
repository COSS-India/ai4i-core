import {
  Box,
  Button,
  Checkbox,
  Flex,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
  Portal,
  Text,
  Tooltip,
} from "@chakra-ui/react";
import { ChevronDownIcon, RepeatIcon, SettingsIcon } from "@chakra-ui/icons";
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
          maxH="min(520px, 70vh)"
          overflowY="auto"
          minW="320px"
          pt={0}
          pb={2}
          zIndex="popover"
        >
          {/* Pinned header: Reset stays reachable while the column list scrolls. */}
          <Box
            position="sticky"
            top={0}
            zIndex={1}
            bg="inherit"
            px={4}
            pt={3}
            pb={2}
            borderBottomWidth="1px"
            borderColor="gray.100"
          >
            <Flex align="center" justify="space-between" gap={3} mb={1}>
              <Text fontSize="sm" fontWeight="semibold" color="ink.700">
                Columns
              </Text>
              <Button
                size="sm"
                variant="outline"
                colorScheme="blue"
                fontSize="sm"
                fontWeight="semibold"
                leftIcon={<RepeatIcon boxSize={3.5} />}
                onClick={onReset}
              >
                Reset to default
              </Button>
            </Flex>
            <Text fontSize="xs" color="ink.500">
              {helper}
            </Text>
            <Text fontSize="xs" color="ink.400">
              {mandatoryHint}
            </Text>
          </Box>
          <Box h={1} />
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
        </MenuList>
      </Portal>
    </Menu>
  );
}

export default AdminListColumnPicker;
