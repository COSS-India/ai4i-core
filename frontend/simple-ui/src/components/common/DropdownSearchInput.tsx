import React from "react";
import { Box, Input, InputGroup, InputLeftElement } from "@chakra-ui/react";
import { SearchIcon } from "@chakra-ui/icons";

/** Case-insensitive "label contains query"; an empty query matches everything. */
export function matchesDropdownSearch(label: string, query: string): boolean {
  const q = query.trim().toLowerCase();
  return !q || label.toLowerCase().includes(q);
}

export type DropdownSearchInputProps = Readonly<{
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  /** Defaults to the placeholder without its trailing dots. */
  ariaLabel?: string;
  inputRef?: React.Ref<HTMLInputElement>;
}>;

/** Search strip at the top of an open dropdown list (icon, input, divider). */
export default function DropdownSearchInput({
  value,
  onChange,
  placeholder,
  ariaLabel,
  inputRef,
}: DropdownSearchInputProps) {
  return (
    <Box px={3} py={2} borderBottomWidth="1px" borderColor="ink.100">
      <InputGroup size="sm">
        <InputLeftElement pointerEvents="none">
          <SearchIcon color="ink.400" />
        </InputLeftElement>
        <Input
          ref={inputRef}
          placeholder={placeholder}
          aria-label={ariaLabel ?? placeholder.replace(/[.…]+$/, "")}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          bg="white"
        />
      </InputGroup>
    </Box>
  );
}
