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
import React, { useEffect, useRef, useState } from "react";
import { METERING } from "../../config/meteringConstants";
import type { MeteringDateRange, MeteringDayKey } from "../../types/metering";
import {
  buildCalendarWeeks,
  clampMonth,
  compareMonths,
  formatCalendarMonth,
  formatMeteringDateRange,
  formatMonthName,
  istDayKey,
  monthOfDayKey,
  shiftMonth,
  type MeteringCalendarMonth,
} from "../../utils/meteringDateRange";

interface CustomRangePickerProps {
  appliedRange: MeteringDateRange | null;
  onApply: (range: MeteringDateRange) => void;
  onClear: () => void;
}

const MONTH_INDEXES = Array.from({ length: 12 }, (_, i) => i);

/** Day cell colours: a selected start/end, a day inside the range, or neither. */
const DAY_STYLES = {
  endpoint: { bg: "orange.500", color: "white" },
  inRange: { bg: "orange.50", color: "orange.700" },
  default: { bg: "transparent", color: "gray.700" },
} as const;

interface DayCellState {
  isDisabled: boolean;
  isEndpoint: boolean;
  style: (typeof DAY_STYLES)[keyof typeof DAY_STYLES];
}

/**
 * Future days are never pickable. While the end is being picked, days before
 * the start are disabled in both calendars.
 */
function getDayCellState(
  day: MeteringDayKey,
  today: MeteringDayKey,
  start: MeteringDayKey | null,
  end: MeteringDayKey | null,
  rangeEnd: MeteringDayKey | null,
): DayCellState {
  const isDisabled = day > today || (start != null && end == null && day < start);
  const isEndpoint = day === start || day === end;
  const isInRange = !!start && !!rangeEnd && day > start && day < rangeEnd;
  return { isDisabled, isEndpoint, style: dayStyleFor(isEndpoint, isInRange) };
}

function dayStyleFor(isEndpoint: boolean, isInRange: boolean): DayCellState["style"] {
  if (isEndpoint) return DAY_STYLES.endpoint;
  if (isInRange) return DAY_STYLES.inRange;
  return DAY_STYLES.default;
}

/** What a calendar shows: its day grid, or the year / month lists for jumping far back. */
type CalendarView = "days" | "years" | "months";

interface CalendarMonthProps {
  month: MeteringCalendarMonth;
  /** Inclusive bounds this calendar may show. */
  minMonth: MeteringCalendarMonth;
  maxMonth: MeteringCalendarMonth;
  onMonthChange: (month: MeteringCalendarMonth) => void;
  today: MeteringDayKey;
  start: MeteringDayKey | null;
  end: MeteringDayKey | null;
  hoverDay: MeteringDayKey | null;
  onSelect: (day: MeteringDayKey) => void;
  onHover: (day: MeteringDayKey | null) => void;
}

const CalendarMonth: React.FC<CalendarMonthProps> = ({
  month,
  minMonth,
  maxMonth,
  onMonthChange,
  today,
  start,
  end,
  hoverDay,
  onSelect,
  onHover,
}) => {
  const copy = METERING.CUSTOM_RANGE;
  const [view, setView] = useState<CalendarView>("days");
  const [pickedYear, setPickedYear] = useState(month.year);
  const titleRef = useRef<HTMLButtonElement>(null);
  // The selected year / month button, focused and scrolled to when its list opens.
  const currentOptionRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (view === "days") return;
    currentOptionRef.current?.focus();
    currentOptionRef.current?.scrollIntoView?.({ block: "center" });
  }, [view]);

  // A month change from outside (the ‹ › arrows) closes an open year / month
  // list, so the title and grid never show a stale year.
  useEffect(() => {
    setView("days");
  }, [month.year, month.month]);

  // While the end is being picked, preview the range up to the hovered day.
  const rangeEnd = end ?? (start && hoverDay && hoverDay >= start ? hoverDay : null);

  const years = Array.from(
    { length: maxMonth.year - minMonth.year + 1 },
    (_, i) => minMonth.year + i,
  );
  const isMonthOutOfRange = (m: number) =>
    compareMonths({ year: pickedYear, month: m }, minMonth) < 0 ||
    compareMonths({ year: pickedYear, month: m }, maxMonth) > 0;

  // Title toggles days → years; from months it steps back to years.
  const handleTitleClick = () => {
    if (view === "days") {
      setPickedYear(month.year);
      setView("years");
    } else {
      setView(view === "months" ? "years" : "days");
    }
  };

  const handleYearPick = (year: number) => {
    setPickedYear(year);
    setView("months");
  };

  const handleMonthPick = (m: number) => {
    onMonthChange(clampMonth({ year: pickedYear, month: m }, minMonth, maxMonth));
    setView("days");
    titleRef.current?.focus();
  };

  // Esc steps back a level instead of closing the whole popover.
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== "Escape" || view === "days") return;
    e.stopPropagation();
    setView(view === "months" ? "years" : "days");
    if (view === "years") titleRef.current?.focus();
  };

  const renderYears = () => (
    <Box h="252px" overflowY="auto">
      <SimpleGrid columns={4} spacing={1}>
        {years.map((y) => (
          <Button
            key={y}
            ref={y === month.year ? currentOptionRef : undefined}
            size="sm"
            variant={y === month.year ? "solid" : "ghost"}
            colorScheme={y === month.year ? "orange" : "gray"}
            fontWeight={y === month.year ? "semibold" : "normal"}
            onClick={() => handleYearPick(y)}
          >
            {y}
          </Button>
        ))}
      </SimpleGrid>
    </Box>
  );

  const renderMonths = () => {
    // Focus the shown month, or the first pickable one in another year.
    const focusMonth =
      pickedYear === month.year
        ? month.month
        : MONTH_INDEXES.find((i) => !isMonthOutOfRange(i));
    return (
      <SimpleGrid columns={3} spacing={2} h="252px" alignContent="center">
        {MONTH_INDEXES.map((m) => {
          const isCurrent = pickedYear === month.year && m === month.month;
          return (
            <Button
              key={m}
              ref={m === focusMonth ? currentOptionRef : undefined}
              h={12}
              variant={isCurrent ? "solid" : "ghost"}
              colorScheme={isCurrent ? "orange" : "gray"}
              fontWeight={isCurrent ? "semibold" : "normal"}
              isDisabled={isMonthOutOfRange(m)}
              onClick={() => handleMonthPick(m)}
            >
              {formatMonthName(m)}
            </Button>
          );
        })}
      </SimpleGrid>
    );
  };

  const renderDays = () => (
    <SimpleGrid columns={7} spacingY={1}>
      {copy.WEEKDAYS.map((d) => (
        <Text key={d} textAlign="center" fontSize="xs" color="gray.500" py={1}>
          {d}
        </Text>
      ))}
      {buildCalendarWeeks(month).flat().map((day, i) => {
        if (!day) return <Box key={`pad-${i}`} />;
        const { isDisabled, isEndpoint, style } = getDayCellState(
          day,
          today,
          start,
          end,
          rangeEnd,
        );
        return (
          <Button
            key={day}
            size="sm"
            variant="ghost"
            h={9}
            minW={9}
            px={0}
            fontWeight={isEndpoint || day === today ? "semibold" : "normal"}
            borderRadius={isEndpoint ? "full" : "md"}
            bg={style.bg}
            color={style.color}
            borderWidth={day === today && !isEndpoint ? "1px" : 0}
            borderColor="orange.400"
            _hover={{ bg: isEndpoint ? "orange.600" : "orange.100" }}
            isDisabled={isDisabled}
            aria-label={day}
            aria-pressed={isEndpoint}
            onClick={() => onSelect(day)}
            onMouseEnter={() => onHover(day)}
            onMouseLeave={() => onHover(null)}
          >
            {Number(day.slice(8))}
          </Button>
        );
      })}
    </SimpleGrid>
  );

  let body: React.ReactNode;
  if (view === "years") body = renderYears();
  else if (view === "months") body = renderMonths();
  else body = renderDays();

  return (
    <VStack
      align="stretch"
      spacing={2}
      minW="252px"
      role="group"
      aria-label={formatCalendarMonth(month)}
      onKeyDown={handleKeyDown}
    >
      <Button
        ref={titleRef}
        size="sm"
        variant="ghost"
        alignSelf="center"
        fontWeight="semibold"
        color="gray.800"
        rightIcon={view === "days" ? <ChevronDownIcon /> : <ChevronUpIcon />}
        aria-expanded={view !== "days"}
        title={copy.CHOOSE_MONTH_YEAR}
        onClick={handleTitleClick}
      >
        {view === "months" ? pickedYear : formatCalendarMonth(month)}
      </Button>
      {body}
    </VStack>
  );
};

/** "Custom range" time filter: a two-month IST calendar with Apply / Cancel. */
const CustomRangePicker: React.FC<CustomRangePickerProps> = ({
  appliedRange,
  onApply,
  onClear,
}) => {
  const copy = METERING.CUSTOM_RANGE;
  const { isOpen, onOpen, onClose } = useDisclosure();
  const [today, setToday] = useState(() => istDayKey(Date.now()));
  // The calendars move independently: picking a month in one never shifts the
  // other. The right is never earlier than the left (the same month is fine,
  // e.g. to pick the end date there), and at most this month.
  const [leftMonth, setLeftMonth] = useState(() => shiftMonth(monthOfDayKey(today), -1));
  const [rightMonth, setRightMonth] = useState(() => monthOfDayKey(today));
  const [start, setStart] = useState<MeteringDayKey | null>(null);
  const [end, setEnd] = useState<MeteringDayKey | null>(null);
  const [hoverDay, setHoverDay] = useState<MeteringDayKey | null>(null);

  const currentMonth = monthOfDayKey(today);
  const leftMin: MeteringCalendarMonth = { year: copy.MIN_YEAR, month: 0 };
  const leftMax = rightMonth;
  const rightMin = leftMonth;
  // The arrows step both calendars together, keeping the gap between them.
  const canGoBack = compareMonths(leftMonth, leftMin) > 0;
  const canGoForward = compareMonths(rightMonth, currentMonth) < 0;
  const stepBoth = (delta: number) => {
    setLeftMonth((m) => shiftMonth(m, delta));
    setRightMonth((m) => shiftMonth(m, delta));
  };

  // Every open starts fresh: previous + current month, nothing preselected.
  const handleOpen = () => {
    const now = istDayKey(Date.now());
    setToday(now);
    setLeftMonth(shiftMonth(monthOfDayKey(now), -1));
    setRightMonth(monthOfDayKey(now));
    setStart(null);
    setEnd(null);
    setHoverDay(null);
    onOpen();
  };

  // Either calendar: first click sets the start, second the end (never before
  // the start, which is disabled meanwhile), a third starts over.
  const handleSelect = (day: MeteringDayKey) => {
    if (!start || end) {
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
                    isDisabled={!canGoBack}
                    onClick={() => stepBoth(-1)}
                  />
                  <IconButton
                    size="sm"
                    variant="outline"
                    aria-label={copy.NEXT_MONTH}
                    icon={<ChevronRightIcon />}
                    isDisabled={!canGoForward}
                    onClick={() => stepBoth(1)}
                  />
                </HStack>
              </HStack>
              <Divider />
              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={6} px={5} pt={4} pb={4}>
                {[leftMonth, rightMonth].map((month, index) => (
                  <CalendarMonth
                    // Keyed by position, so the title keeps focus when its month changes.
                    key={index === 0 ? "left" : "right"}
                    month={month}
                    minMonth={index === 0 ? leftMin : rightMin}
                    maxMonth={index === 0 ? leftMax : currentMonth}
                    onMonthChange={index === 0 ? setLeftMonth : setRightMonth}
                    today={today}
                    start={start}
                    end={end}
                    hoverDay={hoverDay}
                    onSelect={handleSelect}
                    onHover={setHoverDay}
                  />
                ))}
              </SimpleGrid>
              <Divider />
              <HStack justify="flex-end" px={5} py={3}>
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
