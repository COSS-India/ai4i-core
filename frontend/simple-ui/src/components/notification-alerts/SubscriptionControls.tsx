import {
  Box,
  Button,
  Checkbox,
  HStack,
  Input,
  InputGroup,
  InputLeftElement,
  Drawer,
  DrawerBody,
  DrawerCloseButton,
  DrawerContent,
  DrawerFooter,
  DrawerHeader,
  DrawerOverlay,
  Spinner,
  Tag,
  Text,
  Tooltip,
  useDisclosure,
  VStack,
} from "@chakra-ui/react";
import { SearchIcon } from "@chakra-ui/icons";
import React, { useMemo, useState } from "react";
import { FiBell, FiBellOff, FiMail, FiUserPlus } from "react-icons/fi";
import { INSTITUTION } from "../../config/constants";
import ConfirmDialog from "../common/ConfirmDialog";
import type { ThresholdBand } from "../../types/notificationAlerts";
import type { TenantUserView } from "../../types/tenant";

interface SubscriptionToggleProps {
  subscribed: boolean;
  /** Mandatory (GLOBAL) row — always subscribed, no opt-out. */
  locked: boolean;
  rowLabel: string;
  onChange: (subscribed: boolean) => void;
}

/**
 * The "My emails" pill. Unsubscribed rows show "Subscribe". Subscribed
 * optional rows show "Subscribed" and turn into a red "Unsubscribe" on
 * hover/focus, so the click's effect is visible before it happens.
 * Subscribe asks for confirmation first; the change still only lands in
 * the row draft, saved by the page's Submit.
 * Mandatory rows are a disabled "Subscribed" with an explanatory tooltip.
 */
export const SubscriptionToggle: React.FC<SubscriptionToggleProps> = ({
  subscribed,
  locked,
  rowLabel,
  onChange,
}) => {
  const [isHovered, setIsHovered] = useState(false);
  const confirmSubscribe = useDisclosure();
  const isOn = locked || subscribed;
  const showUnsubscribe = isOn && !locked && isHovered;

  const tone = !isOn
    ? { bg: "white", borderColor: "ink.200", color: "ink.800" }
    : showUnsubscribe
      ? { bg: "red.50", borderColor: "red.300", color: "red.600" }
      : { bg: "green.50", borderColor: "green.300", color: "green.700" };

  const label = !isOn ? "Subscribe" : showUnsubscribe ? "Unsubscribe" : "Subscribed";

  const button = (
    <Button
      size="sm"
      borderRadius="full"
      variant="outline"
      {...tone}
      _hover={{ ...tone, bg: isOn ? tone.bg : "ink.50" }}
      leftIcon={showUnsubscribe ? <FiBellOff /> : <FiBell />}
      isDisabled={locked}
      aria-pressed={isOn}
      aria-label={`${isOn ? "Unsubscribe from" : "Subscribe to"} ${rowLabel}`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onFocus={() => setIsHovered(true)}
      onBlur={() => setIsHovered(false)}
      onClick={() => {
        // Otherwise a fresh Subscribe click, with the pointer still on the
        // pill, would instantly read "Unsubscribe".
        setIsHovered(false);
        if (subscribed) {
          onChange(false);
        } else {
          confirmSubscribe.onOpen();
        }
      }}
    >
      {label}
    </Button>
  );

  if (!locked) {
    return (
      <>
        {button}
        <ConfirmDialog
          isOpen={confirmSubscribe.isOpen}
          onClose={confirmSubscribe.onClose}
          onConfirm={() => {
            confirmSubscribe.onClose();
            onChange(true);
          }}
          title={`Subscribe to "${rowLabel}"?`}
          body="You'll start receiving this by email."
          confirmLabel="Subscribe"
          confirmColorScheme="blue"
          isCentered
        />
      </>
    );
  }
  return (
    <Tooltip
      label={`Mandatory — every ${INSTITUTION} Admin receives this automatically and can't unsubscribe.`}
      hasArrow
      shouldWrapChildren
    >
      {button}
    </Tooltip>
  );
};

function userDisplayName(user: TenantUserView): string {
  return (
    user.full_name?.trim() ||
    user.username?.trim() ||
    user.email?.trim() ||
    `User ${user.user_id}`
  );
}

interface RecipientsPickerProps {
  /** Selected user ids. */
  value: string[];
  onChange: (recipients: string[]) => void;
  /** Active users of this institution that may be picked. */
  users: TenantUserView[];
  /**
   * Users the send path emails regardless (Institution Admins). Ids of
   * theirs already in `value` are hidden, not counted, and kept on apply.
   */
  alreadyNotifiedIds: ReadonlySet<string>;
  isLoadingUsers: boolean;
  /** Set when loading `users` failed; shown in the drawer with a Retry. */
  usersError: string | null;
  /** `users` is empty only because everyone left is an Institution Admin. */
  onlyAdminsLeft: boolean;
  /** Called each time the drawer opens — re-fetches `users`. */
  onOpen: () => void;
  /** Unsubscribed in the draft — nobody is notified, so picking is paused. */
  isDisabled: boolean;
  rowLabel: string;
  /** The row's delivery channel, shown as a chip in the drawer header. */
  channel: string;
}

const CHANNEL_LABELS: Record<string, string> = { EMAIL: "Email" };

/**
 * "Also Notify In Your Org" — the row's trigger button plus a right-side
 * drawer listing the institution's active users. Picks are staged inside
 * the drawer and only reach the row draft on Done (Cancel drops them);
 * the page's Submit then saves them. Saved ids that are no longer in
 * `users` (deactivated since) stay listed so they can be removed — the API
 * rejects a PUT that still contains one.
 */
export const RecipientsPicker: React.FC<RecipientsPickerProps> = ({
  value,
  onChange,
  users,
  alreadyNotifiedIds,
  isLoadingUsers,
  usersError,
  onlyAdminsLeft,
  onOpen,
  isDisabled,
  rowLabel,
  channel,
}) => {
  const drawer = useDisclosure();
  const [query, setQuery] = useState("");

  // Split the saved list: ids the send path covers anyway stay out of the
  // drawer and the count, and go back in untouched on apply.
  const hiddenIds = value.filter((id) => alreadyNotifiedIds.has(id));
  const addedIds = value.filter((id) => !alreadyNotifiedIds.has(id));
  const [staged, setStaged] = useState<string[]>(addedIds);

  const selected = useMemo(() => new Set(staged), [staged]);
  const knownIds = useMemo(() => new Set(users.map((u) => u.user_id)), [users]);
  const unknownIds = staged.filter((id) => !knownIds.has(id));

  const visibleUsers = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return users;
    return users.filter(
      (u) =>
        (u.full_name ?? "").toLowerCase().includes(q) ||
        (u.username ?? "").toLowerCase().includes(q) ||
        (u.email ?? "").toLowerCase().includes(q),
    );
  }, [query, users]);

  const open = () => {
    setStaged(addedIds);
    setQuery("");
    onOpen();
    drawer.onOpen();
  };

  const apply = () => {
    onChange([...hiddenIds, ...staged]);
    drawer.onClose();
  };

  const toggle = (id: string, checked: boolean) => {
    setStaged((prev) => (checked ? [...prev, id] : prev.filter((v) => v !== id)));
  };

  const count = addedIds.length;
  const label = count === 0 ? "Add people" : `${count} added`;

  return (
    <VStack align="start" spacing={1} maxW="180px">
      <Button
        size="sm"
        borderRadius="full"
        variant="outline"
        leftIcon={<FiUserPlus />}
        isDisabled={isDisabled}
        onClick={open}
        aria-label={`Additional recipients for ${rowLabel}: ${label}`}
      >
        {label}
      </Button>
      {isDisabled ? (
        <Text fontSize="xs" color="ink.600">
          Unsubscribed — no one is notified.
          {count > 0
            ? ` ${count} saved ${count === 1 ? "person resumes" : "people resume"} when you subscribe.`
            : null}
        </Text>
      ) : null}

      <Drawer isOpen={drawer.isOpen} onClose={drawer.onClose} placement="right" size="sm">
        <DrawerOverlay />
        <DrawerContent>
          <DrawerCloseButton top={4} />
          <DrawerHeader pb={2}>
            <Text fontSize="xs" fontWeight="semibold" color="blue.600" letterSpacing="wide">
              ALSO NOTIFY IN YOUR ORG
            </Text>
            <Text fontSize="lg" fontWeight="semibold" mt={1}>
              {rowLabel}
            </Text>
            <Text fontSize="sm" fontWeight="normal" color="ink.600" mt={2}>
              Add other people in your organisation who should receive this too.
            </Text>
            <Tag size="md" borderRadius="full" variant="outline" mt={3} gap={1.5}>
              <FiMail />
              <Text as="span" fontSize="xs" color="ink.800">
                {CHANNEL_LABELS[channel] ?? channel}
              </Text>
              <Text as="span" fontSize="xs" color="ink.500">
                Delivery channel
              </Text>
            </Tag>
          </DrawerHeader>

          <DrawerBody pt={2}>
            <InputGroup mb={3}>
              <InputLeftElement pointerEvents="none">
                <SearchIcon color="ink.400" />
              </InputLeftElement>
              <Input
                placeholder="Search people in your organisation"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                autoFocus
              />
            </InputGroup>
            {isLoadingUsers ? (
              <HStack py={6} justify="center">
                <Spinner size="sm" />
              </HStack>
            ) : usersError ? (
              <VStack align="start" spacing={2} py={2}>
                <Text fontSize="sm" color="red.600">
                  {usersError}
                </Text>
                <Button size="sm" variant="outline" onClick={onOpen}>
                  Retry
                </Button>
              </VStack>
            ) : (
              <VStack align="stretch" spacing={0}>
                {unknownIds.map((id) => (
                  <Checkbox key={id} isChecked onChange={() => toggle(id, false)} py={2.5} px={1}>
                    <Text as="span" fontSize="sm" color="ink.600">
                      Inactive user — untick to remove
                    </Text>
                  </Checkbox>
                ))}
                {visibleUsers.map((user) => (
                  <Checkbox
                    key={user.user_id}
                    isChecked={selected.has(user.user_id)}
                    onChange={(e) => toggle(user.user_id, e.target.checked)}
                    py={2.5}
                    px={1}
                  >
                    <Text as="span" display="block" fontSize="sm" fontWeight="semibold" noOfLines={1}>
                      {userDisplayName(user)}
                    </Text>
                    <Text as="span" display="block" fontSize="xs" color="ink.600" noOfLines={1}>
                      {user.email}
                    </Text>
                  </Checkbox>
                ))}
                {visibleUsers.length === 0 && unknownIds.length === 0 ? (
                  <Text fontSize="sm" color="ink.600" py={2}>
                    {users.length > 0
                      ? "No people match your search."
                      : onlyAdminsLeft
                        ? "Everyone else in your organisation is an Institution Admin and already receives this."
                        : "No other active people in your organisation."}
                  </Text>
                ) : null}
              </VStack>
            )}
          </DrawerBody>

          <DrawerFooter borderTopWidth="1px" borderColor="ink.200" justifyContent="space-between">
            <Text fontSize="sm" color="ink.600">
              {staged.length} selected
            </Text>
            <HStack spacing={2}>
              <Button variant="ghost" onClick={drawer.onClose}>
                Cancel
              </Button>
              <Button colorScheme="blue" onClick={apply}>
                Done
              </Button>
            </HStack>
          </DrawerFooter>
        </DrawerContent>
      </Drawer>
    </VStack>
  );
};

/** Read-only chips of the bands the Adopter Admin has turned on. */
export const ThresholdChips: React.FC<{ bands?: ThresholdBand[] }> = ({ bands }) => {
  if (!bands) {
    return (
      <Text fontSize="sm" color="ink.600">
        —
      </Text>
    );
  }
  const active = bands
    .filter((band) => band.active)
    .sort((a, b) => a.percentage - b.percentage);
  if (active.length === 0) {
    return (
      <Text fontSize="sm" color="ink.600">
        None active
      </Text>
    );
  }
  return (
    <HStack spacing={1.5} flexWrap="wrap" maxW="150px" rowGap={1.5}>
      {active.map((band) => (
        <Tag key={band.percentage} size="sm" borderRadius="full" fontWeight="semibold">
          {band.percentage}%
        </Tag>
      ))}
    </HStack>
  );
};
