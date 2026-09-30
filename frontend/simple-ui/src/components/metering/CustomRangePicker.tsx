import {
  Box,
  Button,
  Divider,
  HStack,
  IconButton,
  Popover,
  PopoverBody,
  PopoverContent,
  PopoverTrigger,
  Portal,
  SimpleGrid,
  Text,
  Tooltip,
  VStack,
  useDisclosure,
} from "@chakra-ui/react";
import {
  CalendarIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ChevronUpIcon,
  SmallCloseIcon,
} from "@chakra-ui/icons";
import React, { useState } from "react";
import { METERING } from "../../config/meteringConstants";
import type { MeteringDateRange, MeteringDayKey } from "../../types/metering";
import {
  buildCalendarWeeks,
  compareMonths,
  formatCalendarMonth,
  formatMeteringDateRange,
  istDayKey,
  monthOfDayKey,
  shiftMonth,
  type MeteringCalendarMonth,
} from "../../utils/meteringDateRange";

interface CustomRangePickerProps {
  appliedRange: MeteringDateRange | null;
  /** Earliest selectable IST date; the picker is unavailable until it is known. */
  earliestDay: MeteringDayKey | null;
  onApply: (range: MeteringDateRange) => void;
  onClear: () => void;
}

interface CalendarMonthProps {
  month: MeteringCalendarMonth;
  today: MeteringDayKey;
  earliestDay: MeteringDayKey | null;
  start: MeteringDayKey | null;
  end: MeteringDayKey | null;
  hoverDay: MeteringDayKey | null;
  onSelect: (day: MeteringDayKey) => void;
  onHover: (day: MeteringDayKey | null) => void;
}

const CalendarMonth: React.FC<CalendarMonthProps> = ({
  month,
  today,
  earliestDay,
  start,
  end,
  hoverDay,
  onSelect,
  onHover,
}) => {
  const copy = METERING.CUSTOM_RANGE;
  // While only the start is picked, preview the range up to the hovered day.
  const rangeEnd = end ?? (start && hoverDay && hoverDay >= start ? hoverDay : null);

  return (
    <VStack align="stretch" spacing={2} minW="252px">
      <Text textAlign="center" fontWeight="semibold" color="gray.800">
        {formatCalendarMonth(month)}
      </Text>
      <SimpleGrid columns={7} spacingY={1}>
        {copy.WEEKDAYS.map((d) => (
          <Text key={d} textAlign="center" fontSize="xs" color="gray.500" py={1}>
            {d}
          </Text>
        ))}
        {buildCalendarWeeks(month).flat().map((day, i) => {
          if (!day) return <Box key={`pad-${i}`} />;
          const isBeforeData = earliestDay != null && day < earliestDay;
          const isDisabled = day > today || isBeforeData;
          const isEndpoint = day === start || day === end;
          const isInRange = !!start && !!rangeEnd && day > start && day < rangeEnd;
          const dayButton = (
            <Button
              key={day}
              size="sm"
              variant="ghost"
              h={9}
              minW={9}
              px={0}
              fontWeight={isEndpoint || day === today ? "semibold" : "normal"}
              borderRadius={isEndpoint ? "full" : "md"}
              bg={isEndpoint ? "orange.500" : isInRange ? "orange.50" : "transparent"}
              color={isEndpoint ? "white" : isInRange ? "orange.700" : "gray.700"}
              borderWidth={day === today && !isEndpoint ? "1px" : 0}
              borderColor="orange.400"
              _hover={{ bg: isEndpoint ? "orange.600" : "orange.100" }}
              isDisabled={isDisabled}
              // A disabled button swallows hover in some browsers; let the
              // pointer reach the tooltip wrapper instead.
              pointerEvents={isBeforeData ? "none" : undefined}
              aria-label={isBeforeData ? `${day}, ${copy.NO_DATA}` : day}
              aria-pressed={isEndpoint}
              onClick={() => onSelect(day)}
              onMouseEnter={() => onHover(day)}
              onMouseLeave={() => onHover(null)}
            >
              {Number(day.slice(8))}
            </Button>
          );
          if (!isBeforeData) return dayButton;
          return (
            <Tooltip key={day} label={copy.NO_DATA} hasArrow placement="top" openDelay={150}>
              <Box display="flex" justifyContent="center" cursor="not-allowed">
                {dayButton}
              </Box>
            </Tooltip>
          );
        })}
      </SimpleGrid>
    </VStack>
  );
};

/** "Custom range" time filter: a two-month IST calendar with Apply / Cancel. */
const CustomRangePicker: React.FC<CustomRangePickerProps> = ({
  appliedRange,
  earliestDay,
  onApply,
  onClear,
}) => {
  const copy = METERING.CUSTOM_RANGE;
  const { isOpen, onOpen, onClose } = useDisclosure();
  const [today, setToday] = useState(() => istDayKey(Date.now()));
  const [leftMonth, setLeftMonth] = useState(() => shiftMonth(monthOfDayKey(today), -1));
  const [start, setStart] = useState<MeteringDayKey | null>(null);
  const [end, setEnd] = useState<MeteringDayKey | null>(null);
  const [hoverDay, setHoverDay] = useState<MeteringDayKey | null>(null);

  const rightMonth = shiftMonth(leftMonth, 1);
  // Earlier months stay reachable; their days are disabled with a "No data
  // available" hint rather than hiding the months.
  const canGoForward = compareMonths(rightMonth, monthOfDayKey(today)) < 0;

  // Every open starts fresh: previous + current month, nothing preselected.
  const handleOpen = () => {
    const now = istDayKey(Date.now());
    setToday(now);
    setLeftMonth(shiftMonth(monthOfDayKey(now), -1));
    setStart(null);
    setEnd(null);
    setHoverDay(null);
    onOpen();
  };

  const handleSelect = (day: MeteringDayKey) => {
    if (!start || end || day < start) {
      setStart(day);
      setEnd(null);
      return;
    }
    setEnd(day);
  };

  const handleApply = () => {
    if (!start || !end) return;
    onApply({ from: start, to: end });
    onClose();
  };

  const status = start && end
    ? formatMeteringDateRange({ from: start, to: end })
    : start
      ? copy.SELECT_END
      : copy.SELECT_START;

  const isActive = appliedRange != null;

  return (
    <HStack spacing={1}>
      <Popover isOpen={isOpen} onOpen={handleOpen} onClose={onClose} placement="bottom-start" isLazy>
        <PopoverTrigger>
          <Button
            size="sm"
            borderRadius="full"
            leftIcon={<CalendarIcon />}
            rightIcon={isOpen ? <ChevronUpIcon /> : <ChevronDownIcon />}
            colorScheme={isActive || isOpen ? "orange" : "gray"}
            variant={isActive ? "solid" : "outline"}
            fontWeight={isActive ? "semibold" : "normal"}
            isDisabled={earliestDay == null}
          >
            {appliedRange ? formatMeteringDateRange(appliedRange) : METERING.CONTROLS.CUSTOM_RANGE}
          </Button>
        </PopoverTrigger>
        <Portal>
          <PopoverContent w="auto" maxW="calc(100vw - 32px)" borderRadius="lg" shadow="lg">
            <PopoverBody p={0}>
              <HStack justify="space-between" align="flex-start" px={5} pt={4} pb={3} spacing={4}>
                <Box>
                  <Text fontWeight="semibold" color="gray.800">{copy.TITLE}</Text>
                  <Text fontSize="xs" color="gray.500">{copy.SUBTITLE}</Text>
                </Box>
                <HStack spacing={2}>
                  <IconButton
                    size="sm"
                    variant="outline"
                    aria-label={copy.PREVIOUS_MONTH}
                    icon={<ChevronLeftIcon />}
                    onClick={() => setLeftMonth((m) => shiftMonth(m, -1))}
                  />
                  <IconButton
                    size="sm"
                    variant="outline"
                    aria-label={copy.NEXT_MONTH}
                    icon={<ChevronRightIcon />}
                    isDisabled={!canGoForward}
                    onClick={() => setLeftMonth((m) => shiftMonth(m, 1))}
                  />
                </HStack>
              </HStack>
              <Divider />
              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={6} px={5} pt={4}>
                {[leftMonth, rightMonth].map((month) => (
                  <CalendarMonth
                    key={`${month.year}-${month.month}`}
                    month={month}
                    today={today}
                    earliestDay={earliestDay}
                    start={start}
                    end={end}
                    hoverDay={hoverDay}
                    onSelect={handleSelect}
                    onHover={setHoverDay}
                  />
                ))}
              </SimpleGrid>
              <Text fontSize="xs" color="gray.600" px={5} pt={3} pb={3} aria-live="polite">
                {status}
              </Text>
              <Divider />
              <HStack justify="space-between" px={5} py={3}>
                <Text fontSize="xs" color="gray.500">{copy.TIME_ZONE_NOTE}</Text>
                <HStack spacing={2}>
                  <Button size="sm" variant="outline" onClick={onClose}>
                    {copy.CANCEL}
                  </Button>
                  <Button size="sm" colorScheme="orange" onClick={handleApply} isDisabled={!start || !end}>
                    {copy.APPLY}
                  </Button>
                </HStack>
              </HStack>
            </PopoverBody>
          </PopoverContent>
        </Portal>
      </Popover>
      {isActive ? (
        <IconButton
          size="xs"
          variant="ghost"
          borderRadius="full"
          aria-label={copy.CLEAR}
          title={copy.CLEAR}
          icon={<SmallCloseIcon />}
          onClick={onClear}
        />
      ) : null}
    </HStack>
  );
};

export default CustomRangePicker;
