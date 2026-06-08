import {
  Box,
  Button,
  Checkbox,
  FormControl,
  FormErrorMessage,
  FormLabel,
  Menu,
  MenuButton,
  MenuDivider,
  MenuItem,
  MenuList,
  Text,
} from "@chakra-ui/react";
import { TARGET_SERVICES } from "../../../../../types/alerting";
import { FORM_REQUIRED_ASTERISK } from "../../constants";
import type { DefinitionFormFieldsProps } from "./types";

export default function DefinitionTargetField({ mode, defs, expandedUpdateServices = [] }: DefinitionFormFieldsProps) {
  const isCreate = mode === "create";
  const category = isCreate ? defs.createForm.category : defs.updateForm.category;
  const selected = isCreate ? (defs.createForm.service ?? []) : expandedUpdateServices;
  const error = isCreate ? defs.createErrors?.service : defs.updateErrors.service;
  const isInvalid = isCreate ? !!defs.createErrors?.service : Boolean(defs.updateErrors.service);

  const setServices = (service: string[]) =>
    isCreate
      ? defs.setCreateForm({ ...defs.createForm, service })
      : defs.setUpdateForm({ ...defs.updateForm, service });

  const labelText = (() => {
    if (selected.length === 0) {
      return <Text color="gray.400">{isCreate ? "Select targets" : "Select targets..."}</Text>;
    }
    if (selected.length === TARGET_SERVICES.length) {
      return <Text color="gray.700">All services selected</Text>;
    }
    if (selected.length === 1) {
      const v = selected[0];
      return <Text color="gray.700">{TARGET_SERVICES.find((t) => t.value === v)?.label ?? v}</Text>;
    }
    return <Text color="gray.700">{`${selected.length} services selected`}</Text>;
  })();

  return (
    <FormControl isRequired={category !== "infrastructure"} isInvalid={isInvalid}>
      <FormLabel fontWeight="semibold" fontSize="sm" requiredIndicator={FORM_REQUIRED_ASTERISK}>
        Target
      </FormLabel>
      {category === "infrastructure" ? (
        <Box
          px={3}
          py={2}
          bg="gray.100"
          borderRadius="md"
          borderWidth="1px"
          borderColor="gray.200"
          color="gray.600"
          fontSize="sm"
        >
          All services (infrastructure monitors the full stack)
        </Box>
      ) : (
        <Menu closeOnSelect={false} matchWidth>
          <MenuButton
            as={Button}
            variant="outline"
            w="100%"
            bg="white"
            color="gray.700"
            borderWidth="1px"
            borderColor="gray.200"
            borderRadius="md"
            fontWeight="normal"
            textAlign="left"
            _hover={{ borderColor: "gray.400" }}
            _active={{ bg: "white" }}
            rightIcon={<Text fontSize="xs" color="gray.500">▾</Text>}
          >
            {labelText}
          </MenuButton>
          <MenuList w="100%" maxH="300px" overflowY="auto">
            <MenuItem closeOnSelect={false} px={4} py={2}>
              <Checkbox
                isChecked={selected.length === TARGET_SERVICES.length}
                isIndeterminate={selected.length > 0 && selected.length < TARGET_SERVICES.length}
                onChange={(e) =>
                  setServices(
                    e.target.checked
                      ? isCreate
                        ? TARGET_SERVICES.map((t) => t.value)
                        : ["all"]
                      : []
                  )
                }
                fontWeight="semibold"
              >
                All services
              </Checkbox>
            </MenuItem>
            <MenuDivider my={1} />
            {TARGET_SERVICES.map((opt) => (
              <MenuItem key={opt.value} closeOnSelect={false} px={4} py={2}>
                <Checkbox
                  isChecked={selected.includes(opt.value)}
                  onChange={(e) => {
                    const next = e.target.checked
                      ? [...selected, opt.value]
                      : selected.filter((s: string) => s !== opt.value);
                    setServices(next);
                  }}
                >
                  {opt.label}
                </Checkbox>
              </MenuItem>
            ))}
          </MenuList>
        </Menu>
      )}
      <FormErrorMessage>{error}</FormErrorMessage>
    </FormControl>
  );
}
