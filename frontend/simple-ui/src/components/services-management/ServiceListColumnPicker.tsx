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
  SERVICE_LIST_COLUMNS,
  canToggleOffServiceListColumn,
  toggleServiceListColumn,
  type ServiceListColumnId,
} from "./serviceListColumns";

type ServiceListColumnPickerProps = {
  visibleIds: readonly ServiceListColumnId[];
  onChange: (next: ServiceListColumnId[]) => void;
  onReset: () => void;
};

const ServiceListColumnPicker: React.FC<ServiceListColumnPickerProps> = ({
  visibleIds,
  onChange,
  onReset,
}) => {
  const helper = FIELD_HINTS.service.columns.helper;

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
            Name and Actions stay visible. At least one other column must remain.
          </Text>
          {SERVICE_LIST_COLUMNS.map((column) => {
            const checked = visibleIds.includes(column.id);
            const locked =
              column.mandatory ||
              (checked && !canToggleOffServiceListColumn(visibleIds, column.id));
            return (
              <MenuItem
                as="div"
                key={column.id}
                closeOnSelect={false}
                isDisabled={locked}
                onClick={() => {
                  if (locked) return;
                  onChange(toggleServiceListColumn(visibleIds, column.id));
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
};

export default ServiceListColumnPicker;
