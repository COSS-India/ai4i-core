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
import { FIELD_HINTS } from "../../config/fieldHints";
import {
  MODEL_LIST_COLUMNS,
  canToggleOffModelListColumn,
  toggleModelListColumn,
  type ModelListColumnDef,
} from "./modelListColumns";

type ModelListColumnPickerProps = {
  columns?: readonly ModelListColumnDef[];
  visibleIds: readonly string[];
  onChange: (next: string[]) => void;
  onReset: () => void;
};

const ModelListColumnPicker: React.FC<
  Readonly<ModelListColumnPickerProps>
> = ({
  columns = MODEL_LIST_COLUMNS,
  visibleIds,
  onChange,
  onReset,
}) => {
  const helper = FIELD_HINTS.model.columns.tip;

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
        <MenuList maxH="360px" overflowY="auto" minW="260px" py={2} zIndex="popover">
          <Text px={3} pb={1} fontSize="xs" color="ink.500" fontWeight="medium">
            {helper}
          </Text>
          <Text px={3} pb={2} fontSize="xs" color="ink.400">
            Name, Version, Task Type, Provider, and Actions stay visible. At least
            one other column must remain.
          </Text>
          {columns.map((column) => {
            const checked = visibleIds.includes(column.id);
            const locked =
              column.mandatory ||
              (checked && !canToggleOffModelListColumn(visibleIds, column.id, columns));
            return (
              <MenuItem
                as="div"
                key={column.id}
                closeOnSelect={false}
                isDisabled={locked}
                onClick={() => {
                  if (locked) return;
                  onChange(toggleModelListColumn(visibleIds, column.id, columns));
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
                    {column.mandatory && (
                      <Text as="span" color="ink.400" ml={1}>
                        (required)
                      </Text>
                    )}
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
};

export default ModelListColumnPicker;
