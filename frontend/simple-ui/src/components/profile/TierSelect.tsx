import { useMemo, useState } from "react";
import {
  Box,
  Button,
  Input,
  InputGroup,
  InputLeftElement,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
  Portal,
  Text,
} from "@chakra-ui/react";
import { ChevronDownIcon, SearchIcon } from "@chakra-ui/icons";
import type { Tier } from "../../types/tierManagement";

export interface TierSelectProps {
  value: string;
  onChange: (tierId: string) => void;
  tierOptions: Tier[];
  serviceMappingsReady: boolean;
  tierIdsWithServices: Set<string>;
  isDisabled?: boolean;
  isInvalid?: boolean;
  fallbackName?: string;
  flex?: number | string;
}

function label(
  tier: Pick<Tier, "id" | "name">,
  ready: boolean,
  withServices: Set<string>,
) {
  return ready && !withServices.has(String(tier.id))
    ? `${tier.name} (no services mapped)`
    : tier.name;
}

/** Searchable tier dropdown shared by Assign Tier and Manage Plan. */
export default function TierSelect({
  value,
  onChange,
  tierOptions,
  serviceMappingsReady,
  tierIdsWithServices,
  isDisabled,
  isInvalid,
  fallbackName,
  flex,
}: TierSelectProps) {
  const [search, setSearch] = useState("");
  const q = search.trim().toLowerCase();
  const filtered = useMemo(
    () =>
      q
        ? tierOptions.filter((t) => (t.name || "").toLowerCase().includes(q))
        : tierOptions,
    [tierOptions, q],
  );
  const selected = value
    ? label(
        tierOptions.find((t) => String(t.id) === String(value)) ?? {
          id: value,
          name: fallbackName || value,
        },
        serviceMappingsReady,
        tierIdsWithServices,
      )
    : "Select a tier";

  return (
    <Menu matchWidth onClose={() => setSearch("")}>
      <MenuButton
        as={Button}
        type="button"
        rightIcon={<ChevronDownIcon />}
        w="full"
        maxW="full"
        flex={flex}
        textAlign="left"
        fontWeight="normal"
        variant="outline"
        bg="white"
        borderColor={isInvalid ? "red.500" : "inherit"}
        _hover={{ borderColor: "gray.300" }}
        fontSize="sm"
        justifyContent="space-between"
        size="sm"
        isDisabled={isDisabled}
        aria-label="Tier"
      >
        <Text as="span" isTruncated display="block" minW={0}>
          {selected}
        </Text>
      </MenuButton>
      <Portal>
        <MenuList maxH="320px" overflow="hidden" p={0} zIndex={1500}>
          <Box px={3} py={2} borderBottomWidth="1px" borderColor="gray.100">
            <InputGroup size="sm">
              <InputLeftElement pointerEvents="none">
                <SearchIcon color="gray.400" />
              </InputLeftElement>
              <Input
                placeholder="Search tiers..."
                aria-label="Search tiers"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onClick={(e) => e.stopPropagation()}
                onKeyDown={(e) => {
                  if (e.key.length === 1 || e.key === "Backspace" || e.key === "Delete" || e.key === " ")
                    e.stopPropagation();
                }}
                bg="white"
              />
            </InputGroup>
          </Box>
          <Box maxH="240px" overflowY="auto" py={1} role="listbox" aria-label="Tiers">
            {filtered.length === 0 ? (
              <Text px={3} py={2} fontSize="sm" color="gray.500">
                {tierOptions.length === 0 ? "No tiers available" : "No tiers match your search"}
              </Text>
            ) : (
              filtered.map((tier) => (
                <MenuItem
                  key={tier.id}
                  role="option"
                  aria-selected={String(tier.id) === String(value)}
                  onClick={() => onChange(String(tier.id))}
                >
                  {label(tier, serviceMappingsReady, tierIdsWithServices)}
                </MenuItem>
              ))
            )}
          </Box>
        </MenuList>
      </Portal>
    </Menu>
  );
}
