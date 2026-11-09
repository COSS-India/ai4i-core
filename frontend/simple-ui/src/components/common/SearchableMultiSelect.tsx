import React, { useState } from "react";
import {
  Checkbox,
  Flex,
  FormControl,
  FormErrorMessage,
  FormHelperText,
  Popover,
  PopoverBody,
  PopoverContent,
  PopoverTrigger,
  Portal,
  Tag,
  TagCloseButton,
  TagLabel,
  Text,
  useDisclosure,
  Wrap,
} from "@chakra-ui/react";
import { ChevronDownIcon } from "@chakra-ui/icons";
import FieldLabel from "./FieldLabel";
import DropdownSearchInput, { matchesDropdownSearch } from "./DropdownSearchInput";

export type SearchableMultiSelectOption = {
  value: string;
  label: string;
  checked: boolean;
};

export type SearchableMultiSelectProps = Readonly<{
  label: string;
  required?: boolean;
  error?: string;
  helper?: string;
  /** Shown in the field when nothing is picked. */
  placeholder: string;
  /** When set, the open list gets a search box that filters options by label. */
  searchPlaceholder?: string;
  noMatchMessage?: string;
  options: SearchableMultiSelectOption[];
  onCheck: (value: string, checked: boolean) => void;
}>;

/**
 * Multi-select: picked options sit as removable chips inside the field and the
 * checkbox list opens below it, optionally with a search box on top.
 */
export default function SearchableMultiSelect({
  label,
  required,
  error,
  helper,
  placeholder,
  searchPlaceholder,
  noMatchMessage = "No matches",
  options,
  onCheck,
}: SearchableMultiSelectProps) {
  const [search, setSearch] = useState("");
  const { isOpen, onToggle, onClose: closeList } = useDisclosure();
  const onClose = () => {
    closeList();
    setSearch("");
  };
  const selected = options.filter((option) => option.checked);
  const visible = options.filter((option) => matchesDropdownSearch(option.label, search));

  let borderColor = "ink.200";
  if (isOpen) borderColor = "blue.500";
  if (error) borderColor = "red.500";

  return (
    <FormControl isInvalid={Boolean(error)}>
      <FieldLabel required={required}>{label}</FieldLabel>
      <Popover isOpen={isOpen} onClose={onClose} placement="bottom-start" matchWidth isLazy>
        <PopoverTrigger>
          <Flex
            role="combobox"
            aria-expanded={isOpen}
            aria-haspopup="listbox"
            aria-label={label}
            tabIndex={0}
            onClick={isOpen ? onClose : onToggle}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " " || e.key === "ArrowDown") {
                e.preventDefault();
                if (isOpen) onClose();
                else onToggle();
              }
            }}
            align="center"
            gap={2}
            minH="40px"
            px={3}
            py={1.5}
            borderWidth="1px"
            borderRadius="md"
            borderColor={borderColor}
            boxShadow={isOpen ? "0 0 0 1px var(--chakra-colors-blue-500)" : undefined}
            bg="white"
            cursor="pointer"
            _hover={{ borderColor: isOpen || error ? borderColor : "ink.300" }}
            _focusVisible={{ borderColor: "blue.500", boxShadow: "0 0 0 1px var(--chakra-colors-blue-500)" }}
          >
            <Wrap flex="1" spacing={1.5}>
              {selected.length === 0 ? (
                <Text fontSize="md" color="ink.400">
                  {placeholder}
                </Text>
              ) : (
                selected.map((option) => (
                  <Tag key={option.value} size="md" colorScheme="blue" borderRadius="full">
                    <TagLabel>{option.label}</TagLabel>
                    <TagCloseButton
                      aria-label={`Remove ${option.label}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onCheck(option.value, false);
                      }}
                    />
                  </Tag>
                ))
              )}
            </Wrap>
            <ChevronDownIcon color="ink.500" boxSize={5} transform={isOpen ? "rotate(180deg)" : undefined} />
          </Flex>
        </PopoverTrigger>
        <Portal>
          <PopoverContent w="auto" boxShadow="md" borderColor="ink.200" _focus={{ boxShadow: "md" }}>
            {searchPlaceholder ? (
              <DropdownSearchInput value={search} onChange={setSearch} placeholder={searchPlaceholder} />
            ) : null}
            <PopoverBody p={1} maxH="220px" overflowY="auto" role="listbox" aria-multiselectable>
              {visible.length === 0 && options.length > 0 ? (
                <Text px={3} py={2} fontSize="sm" color="ink.500">
                  {noMatchMessage}
                </Text>
              ) : null}
              {visible.map((option) => (
                <Checkbox
                  key={option.value}
                  display="flex"
                  py={2}
                  px={3}
                  borderRadius="md"
                  _hover={{ bg: "ink.50" }}
                  isChecked={option.checked}
                  onChange={(e) => onCheck(option.value, e.target.checked)}
                >
                  {option.label}
                </Checkbox>
              ))}
            </PopoverBody>
          </PopoverContent>
        </Portal>
      </Popover>
      {error ? <FormErrorMessage>{error}</FormErrorMessage> : null}
      {helper && !error ? (
        <FormHelperText fontSize="xs" color="ink.500" mt={1}>
          {helper}
        </FormHelperText>
      ) : null}
    </FormControl>
  );
}
