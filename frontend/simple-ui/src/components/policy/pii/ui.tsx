import { AddIcon, LockIcon } from "@chakra-ui/icons";
import {
  Box,
  Button,
  Flex,
  Heading,
  HStack,
  Icon,
  Radio,
  SimpleGrid,
  Switch,
  Text,
} from "@chakra-ui/react";
import React from "react";
import { FiShield } from "react-icons/fi";
import type { RecordStatus } from "./model";

export function FlaskIcon(props: { boxSize?: number }) {
  return (
    <Icon viewBox="0 0 24 24" boxSize={props.boxSize ?? 4} fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M9 2v6L4 20a1 1 0 0 0 1 2h14a1 1 0 0 0 1-2L15 8V2M9 2h6M9 16h6" strokeLinecap="round" strokeLinejoin="round" />
    </Icon>
  );
}

export function ShieldMark({ boxSize = 9 }: { boxSize?: number }) {
  return (
    <Flex
      w={boxSize}
      h={boxSize}
      borderRadius="lg"
      bg="brand.50"
      color="brand.600"
      align="center"
      justify="center"
      flexShrink={0}
    >
      <Icon as={FiShield} boxSize={boxSize > 8 ? 4 : 3.5} />
    </Flex>
  );
}

export function StatusToggle({
  status,
  effective,
  locked,
  onToggle,
  label,
}: {
  status: RecordStatus;
  effective: RecordStatus;
  locked?: boolean;
  onToggle: () => void;
  label: string;
}) {
  const active = effective === "Active";
  return (
    <HStack spacing={1.5} onClick={(event) => event.stopPropagation()}>
      <Switch
        size="sm"
        colorScheme="green"
        isChecked={status === "Active"}
        isDisabled={locked}
        onChange={onToggle}
        aria-label={label}
      />
      <Text fontSize="xs" fontWeight="medium" color={active ? "green.600" : "ink.400"}>
        {active ? "Active" : "Inactive"}
      </Text>
    </HStack>
  );
}

export function NavCard({
  title,
  description,
  meta,
  status,
  effective,
  locked,
  lockedNote,
  icon,
  onOpen,
  onToggle,
}: {
  title: string;
  description: string;
  meta?: string;
  status: RecordStatus;
  effective: RecordStatus;
  locked?: boolean;
  lockedNote?: string;
  icon: "shield" | "flask";
  onOpen: () => void;
  onToggle?: () => void;
}) {
  const inactive = effective === "Inactive";
  return (
    <Box
      bg="white"
      borderWidth="1px"
      borderColor="ink.200"
      borderRadius="lg"
      p={5}
      opacity={inactive ? 0.6 : 1}
      transition="border-color 0.2s, box-shadow 0.2s"
      _hover={{ borderColor: "brand.200", boxShadow: "sm" }}
    >
      <Flex justify="space-between" align="flex-start" mb={3}>
        {icon === "shield" ? (
          <ShieldMark boxSize={10} />
        ) : (
          <Flex
            w={10}
            h={10}
            borderRadius="lg"
            bg="brand.50"
            color="brand.600"
            align="center"
            justify="center"
          >
            <FlaskIcon />
          </Flex>
        )}
        {onToggle ? (
          <StatusToggle
            status={status}
            effective={effective}
            locked={locked}
            onToggle={onToggle}
            label={`${inactive ? "Activate" : "Deactivate"} ${title}`}
          />
        ) : (
          <Text fontSize="xs" fontWeight="medium" color={inactive ? "ink.400" : "green.600"}>
            {inactive ? "Inactive" : "Active"}
          </Text>
        )}
      </Flex>
      <Button
        variant="ghost"
        onClick={onOpen}
        w="full"
        h="auto"
        p={0}
        justifyContent="flex-start"
        textAlign="left"
        whiteSpace="normal"
        _hover={{ bg: "transparent" }}
      >
        <Box>
          <Heading as="h3" size="sm" mb={1} color="ink.800">
            {title}
          </Heading>
          <Text fontSize="xs" color="ink.500" fontWeight="normal" lineHeight="tall">
            {description}
          </Text>
        </Box>
      </Button>
      {locked && status === "Active" && lockedNote ? (
        <HStack mt={2} spacing={1} color="orange.600">
          <LockIcon boxSize={3} />
          <Text fontSize="xs">{lockedNote}</Text>
        </HStack>
      ) : null}
      {meta ? (
        <Text fontSize="xs" color="ink.500" mt={3} pt={3} borderTopWidth="1px" borderColor="ink.200">
          {meta}
        </Text>
      ) : null}
    </Box>
  );
}

export function AddCard({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <Button
      variant="outline"
      onClick={onClick}
      h="auto"
      minH="148px"
      borderStyle="dashed"
      borderColor="ink.300"
      flexDirection="column"
      gap={2}
      py={5}
      _hover={{ borderColor: "brand.300", bg: "brand.50" }}
    >
      <Flex w={9} h={9} borderRadius="full" bg="ink.100" align="center" justify="center" color="ink.500">
        <AddIcon boxSize={3} />
      </Flex>
      <Text fontSize="sm" fontWeight="medium" color="ink.500">
        {label}
      </Text>
    </Button>
  );
}

export function CardGrid({ children }: { children: React.ReactNode }) {
  return (
    <SimpleGrid columns={{ base: 1, sm: 2, lg: 3 }} spacing={4}>
      {children}
    </SimpleGrid>
  );
}

export function ChoiceCard({
  title,
  description,
  checked,
  onSelect,
  name,
}: {
  title: string;
  description?: string;
  checked: boolean;
  onSelect: () => void;
  name: string;
}) {
  return (
    <Box
      as="label"
      display="flex"
      alignItems={description ? "flex-start" : "center"}
      gap={2.5}
      borderWidth="1px"
      borderColor={checked ? "brand.300" : "ink.200"}
      bg={checked ? "brand.50" : "white"}
      borderRadius="md"
      p={3}
      cursor="pointer"
    >
      <Radio name={name} isChecked={checked} onChange={onSelect} mt={description ? 0.5 : 0} />
      <Box>
        <Text fontSize="sm" fontWeight="medium" color="ink.800">
          {title}
        </Text>
        {description ? (
          <Text fontSize="xs" color="ink.500">
            {description}
          </Text>
        ) : null}
      </Box>
    </Box>
  );
}
