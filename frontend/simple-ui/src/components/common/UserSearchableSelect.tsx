import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Box,
  Button,
  Input,
  InputGroup,
  InputLeftElement,
  Popover,
  PopoverBody,
  PopoverContent,
  PopoverTrigger,
  Spinner,
  Text,
  useColorModeValue,
  useDisclosure,
} from "@chakra-ui/react";
import { ChevronDownIcon, SearchIcon } from "@chakra-ui/icons";
import authService from "../../services/authService";
import type { User } from "../../types/auth";
import { PAGINATION } from "../../constants/pagination";

export type UserSearchablePick = Pick<User, "user_id" | "email" | "username" | "full_name">;

const PAGE_SIZE = PAGINATION.USER_LIST_PAGE_SIZE;

function mergeById(a: User[], b: User[]): User[] {
  const m = new Map<string, User>();
  for (const u of a) m.set(u.user_id, u);
  for (const u of b) m.set(u.user_id, u);
  return Array.from(m.values());
}

function formatUserLabel(u: UserSearchablePick): string {
  const name = getUserDisplayName(u);
  const email = (u.email || "").trim();
  if (name && email) return `${name} (${email})`;
  return name || email || `User ${u.user_id}`;
}

function getUserDisplayName(u: Pick<User, "user_id" | "email" | "username" | "full_name">): string {
  const fullName = (u.full_name || "").trim();
  const username = (u.username || "").trim();
  const email = (u.email || "").trim();
  return fullName || username || email || `User ${u.user_id}`;
}

function matchesSearch(u: User, q: string): boolean {
  if (!q.trim()) return true;
  const s = q.trim().toLowerCase();
  return (
    (u.username || "").toLowerCase().includes(s) ||
    (u.email || "").toLowerCase().includes(s) ||
    (u.full_name || "").toLowerCase().includes(s)
  );
}

type PickVariant = {
  variant: "pick";
  value: string | null;
  onChange: (userId: string | null, picked?: UserSearchablePick | null) => void;
  allowClear?: boolean;
};

type FilterVariant = {
  variant: "filter";
  value: string;
  onChange: (next: string) => void;
  allOptionLabel?: string;
};

type Common = {
  seedUsers?: User[];
  /** When true, only `seedUsers` are shown (no global /auth/users pagination). */
  usersFromSeedOnly?: boolean;
  isDisabled?: boolean;
  isLoading?: boolean;
  placeholder?: string;
  size?: "sm" | "md";
  selectedPreview?: UserSearchablePick | null;
};

export type UserSearchableSelectProps = Common & (PickVariant | FilterVariant);

export default function UserSearchableSelect(props: UserSearchableSelectProps) {
  const {
    seedUsers = [],
    usersFromSeedOnly = false,
    isDisabled = false,
    isLoading: isLoadingExternal = false,
    placeholder = "Select a user",
    size = "md",
    selectedPreview = null,
  } = props;

  const { isOpen, onOpen, onClose } = useDisclosure();
  const [search, setSearch] = useState("");
  const [fromApi, setFromApi] = useState<User[]>([]);
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  const fetchingRef = useRef(false);
  const nextOffsetRef = useRef(0);
  const hasMoreRef = useRef(true);
  const initialLoadedRef = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const triggerBg = useColorModeValue("white", "gray.900");
  const menuBg = useColorModeValue("white", "gray.800");
  const borderCol = useColorModeValue("gray.200", "gray.600");
  const rowHoverBg = useColorModeValue("gray.50", "gray.700");

  const mergedUsers = useMemo(
    () => (usersFromSeedOnly ? seedUsers : mergeById(seedUsers, fromApi)),
    [seedUsers, fromApi, usersFromSeedOnly]
  );

  useEffect(() => {
    if (!usersFromSeedOnly) return;
    setFromApi([]);
    hasMoreRef.current = false;
    setHasMore(false);
    initialLoadedRef.current = true;
  }, [usersFromSeedOnly, seedUsers]);

  useEffect(() => {
    const n = seedUsers.length;
    if (n > nextOffsetRef.current) {
      nextOffsetRef.current = n;
    }
  }, [seedUsers.length]);

  const fetchAt = useCallback(async (offset: number) => {
    if (usersFromSeedOnly) return;
    if (fetchingRef.current) return;
    fetchingRef.current = true;
    setLoadingMore(true);
    try {
      const batch = await authService.listUsersPage(offset, PAGE_SIZE);
      setFromApi((prev) => mergeById(prev, batch));
      const next = offset + batch.length;
      nextOffsetRef.current = next;
      const hm = batch.length === PAGE_SIZE;
      hasMoreRef.current = hm;
      setHasMore(hm);
    } catch (e) {
      console.error("Failed to load users page:", e);
      hasMoreRef.current = false;
      setHasMore(false);
    } finally {
      fetchingRef.current = false;
      setLoadingMore(false);
    }
  }, [usersFromSeedOnly]);

  const loadMore = useCallback(() => {
    if (usersFromSeedOnly) return;
    if (!hasMoreRef.current || fetchingRef.current) return;
    return fetchAt(nextOffsetRef.current);
  }, [fetchAt, usersFromSeedOnly]);

  const handleOpen = () => {
    if (usersFromSeedOnly) {
      hasMoreRef.current = false;
      setHasMore(false);
    } else if (!initialLoadedRef.current) {
      initialLoadedRef.current = true;
      const start = seedUsers.length;
      nextOffsetRef.current = start;
      hasMoreRef.current = true;
      setHasMore(true);
      void fetchAt(start);
    }
    onOpen();
  };

  const handleClose = () => {
    setSearch("");
    onClose();
  };

  useEffect(() => {
    if (!isOpen || usersFromSeedOnly) return;
    const root = scrollRef.current;
    const target = sentinelRef.current;
    if (!root || !target) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) void loadMore();
      },
      { root, rootMargin: "64px", threshold: 0.01 }
    );
    io.observe(target);
    return () => io.disconnect();
  }, [isOpen, loadMore, usersFromSeedOnly]);

  const filtered = useMemo(() => {
    const list = mergedUsers.filter((u) => matchesSearch(u, search));
    return list.sort((a, b) => {
      const displayNameOrder = getUserDisplayName(a).localeCompare(getUserDisplayName(b), undefined, {
        sensitivity: "base",
      });
      if (displayNameOrder !== 0) return displayNameOrder;
      const emailOrder = (a.email || "").localeCompare(b.email || "", undefined, { sensitivity: "base" });
      if (emailOrder !== 0) return emailOrder;
      return a.user_id.localeCompare(b.user_id);
    });
  }, [mergedUsers, search]);

  const pickValue = props.variant === "pick" ? props.value : null;

  const displayLabel = useMemo(() => {
    if (props.variant === "filter") {
      if (props.value === "all") return props.allOptionLabel ?? "All Users";
      const id = props.value;
      if (!id) return placeholder;
      const u = mergedUsers.find((x) => x.user_id === id);
      if (u) return formatUserLabel(u);
      return `User ${id}`;
    }
    if (pickValue == null) return placeholder;
    const u = mergedUsers.find((x) => x.user_id === pickValue);
    if (u) return formatUserLabel(u);
    if (selectedPreview && selectedPreview.user_id === pickValue) return formatUserLabel(selectedPreview);
    return `User ${pickValue}`;
  }, [props, pickValue, mergedUsers, selectedPreview, placeholder]);

  const h = size === "sm" ? "32px" : "40px";
  const fontSize = size === "sm" ? "sm" : "md";

  const handlePick = (u: User) => {
    if (props.variant === "pick") {
      props.onChange(u.user_id, { user_id: u.user_id, email: u.email, username: u.username, full_name: u.full_name });
    } else {
      props.onChange(u.user_id);
    }
    handleClose();
  };

  const handlePickAll = () => {
    if (props.variant === "filter") {
      props.onChange("all");
      handleClose();
    }
  };

  const handleClearPick = () => {
    if (props.variant === "pick" && props.allowClear !== false) {
      props.onChange(null, null);
      handleClose();
    }
  };

  const showClearRow =
    props.variant === "pick" && props.allowClear !== false && pickValue != null;

  return (
    <Popover isOpen={isOpen} onOpen={handleOpen} onClose={handleClose} placement="bottom-start" matchWidth>
      <PopoverTrigger>
        <Button
          w="full"
          h={h}
          size={size}
          fontWeight="normal"
          fontSize={fontSize}
          variant="outline"
          isDisabled={isDisabled || isLoadingExternal}
          rightIcon={<ChevronDownIcon />}
          justifyContent="space-between"
          textAlign="left"
          bg={triggerBg}
          borderColor={borderCol}
          _hover={{ bg: triggerBg }}
          _active={{ bg: triggerBg }}
        >
          <Text noOfLines={1} pr={2} color={displayLabel === placeholder ? "gray.500" : "inherit"}>
            {isLoadingExternal ? "Loading users..." : displayLabel}
          </Text>
        </Button>
      </PopoverTrigger>
      <PopoverContent
        boxShadow="md"
        borderColor={borderCol}
        bg={menuBg}
        _focus={{ boxShadow: "md" }}
      >
        <PopoverBody p={2}>
          <InputGroup size={size} mb={2}>
            <InputLeftElement pointerEvents="none" h={size === "sm" ? "32px" : "40px"}>
              <SearchIcon color="gray.400" boxSize={size === "sm" ? 3 : 4} />
            </InputLeftElement>
            <Input
              placeholder="Search by name, email, id..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              bg={triggerBg}
              pl={10}
              autoFocus
            />
          </InputGroup>
          <Box ref={scrollRef} maxH="260px" overflowY="auto" borderWidth="1px" borderRadius="md" borderColor={borderCol}>
            {props.variant === "filter" && (
              <Box
                as="button"
                type="button"
                w="full"
                textAlign="left"
                px={3}
                py={2}
                _hover={{ bg: rowHoverBg }}
                onClick={handlePickAll}
                borderBottomWidth="1px"
                borderColor={borderCol}
              >
                <Text fontSize={fontSize} fontWeight="semibold">
                  {props.allOptionLabel ?? "All Users"}
                </Text>
              </Box>
            )}
            {showClearRow && (
              <Box
                as="button"
                type="button"
                w="full"
                textAlign="left"
                px={3}
                py={2}
                _hover={{ bg: rowHoverBg }}
                onClick={handleClearPick}
                borderBottomWidth="1px"
                borderColor={borderCol}
              >
                <Text fontSize={fontSize} color="gray.500">
                  Clear selection
                </Text>
              </Box>
            )}
            {filtered.map((u) => (
              <Box
                key={u.user_id}
                as="button"
                type="button"
                w="full"
                textAlign="left"
                px={3}
                py={2}
                _hover={{ bg: rowHoverBg }}
                onClick={() => handlePick(u)}
                bg={
                  (props.variant === "pick" && pickValue === u.user_id) ||
                  (props.variant === "filter" && props.value === u.user_id)
                    ? rowHoverBg
                    : undefined
                }
              >
                <Text fontSize={fontSize}>{formatUserLabel(u)}</Text>
              </Box>
            ))}
            {!search.trim() && loadingMore && (
              <Box py={3} textAlign="center">
                <Spinner size="sm" />
              </Box>
            )}
            {props.variant === "pick" &&
              mergedUsers.length === 0 &&
              !loadingMore &&
              !isLoadingExternal &&
              filtered.length === 0 && (
                <Text fontSize="sm" color="gray.500" px={3} py={4} textAlign="center">
                  No users loaded yet.
                </Text>
              )}
            {search.trim() && filtered.length === 0 && (
              <Text fontSize="sm" color="gray.500" px={3} py={4} textAlign="center">
                No matches in loaded users yet. Scroll down to load more, or clear the search.
              </Text>
            )}
            <Box ref={sentinelRef} h="1px" w="full" aria-hidden />
          </Box>
            {!usersFromSeedOnly && !search.trim() && hasMore && !loadingMore && (
            <Text fontSize="xs" color="gray.500" mt={1} px={1}>
              Scroll down to load more
            </Text>
          )}
        </PopoverBody>
      </PopoverContent>
    </Popover>
  );
}
