import { extendTheme } from "@chakra-ui/react";

/**
 * Product visual system — cool slate neutrals, blue primary actions.
 * Service/task-type colours stay independent of the action colour.
 */
const ink = {
  50: "#F4F6FB",
  100: "#E8EEF6",
  200: "#D5DEEA",
  300: "#B3C0D0",
  400: "#7C8BA0",
  500: "#5A6A80",
  600: "#3E4C61",
  700: "#1E293B",
  800: "#0F172A",
  900: "#0B1220",
};

/** Global interaction blue — same scale as Chakra `blue` (not service identity). */
const brand = {
  50: "#EBF8FF",
  100: "#BEE3F8",
  200: "#90CDF4",
  300: "#63B3ED",
  400: "#4299E1",
  500: "#3182CE",
  600: "#2B6CB0",
  700: "#2C5282",
  800: "#2A4365",
  900: "#1A365D",
};

const FONT =
  '"Plus Jakarta Sans", "Inter", system-ui, -apple-system, sans-serif';

const FOCUS_RING = "0 0 0 2px var(--chakra-colors-blue-500)";

/** Danger / warning only. Create/Save/Update use blue even if a page still passes green/ink. */
const SOLID_SEMANTIC = new Set(["red", "orange", "yellow"]);
/** Ghost/outline keep green for publish/success and red for destructive. */
const GHOST_SEMANTIC = new Set(["red", "green", "orange", "yellow", "teal"]);

function alertPalette(status?: string) {
  switch (status) {
    case "success":
      return { bg: "green.50", fg: "green.800", accent: "green.600" };
    case "warning":
      return { bg: "orange.50", fg: "orange.900", accent: "orange.600" };
    case "error":
      return { bg: "red.50", fg: "red.800", accent: "red.600" };
    default:
      return { bg: "blue.50", fg: "blue.800", accent: "blue.600" };
  }
}

function buttonSolid(colorScheme?: string) {
  const c = colorScheme ?? "ink";
  if (SOLID_SEMANTIC.has(c)) {
    return {
      bg: `${c}.600`,
      color: "white",
      _hover: { bg: `${c}.700`, _disabled: { bg: `${c}.600` } },
      _active: { bg: `${c}.800` },
    };
  }
  return {
    bg: "blue.500",
    color: "white",
    _hover: { bg: "blue.600", _disabled: { bg: "blue.500" } },
    _active: { bg: "blue.700" },
  };
}

function buttonOutline(colorScheme?: string) {
  const c = colorScheme ?? "ink";
  if (GHOST_SEMANTIC.has(c)) {
    return {
      border: "1px solid",
      borderColor: `${c}.500`,
      color: `${c}.700`,
      bg: "white",
      _hover: { bg: `${c}.50`, _disabled: { bg: "white" } },
    };
  }
  return {
    border: "1px solid",
    borderColor: "ink.200",
    color: "ink.800",
    bg: "white",
    _hover: { bg: "ink.50", borderColor: "ink.300", _disabled: { bg: "white" } },
    _active: { bg: "ink.100" },
  };
}

const customTheme = extendTheme({
  colors: {
    ink,
    brand,
    primary: ink,
    light: {
      100: "#F4F6FB",
      200: "#FFFFFF",
    },
    dark: {
      100: "#0F172A",
      200: "#1E293B",
    },
    /** Kept for existing create-toolbar call sites. */
    create: {
      50: "#F4F6FB",
      100: "#E8EEF6",
      200: "#D5DEEA",
      300: "#B3C0D0",
      400: "#7C8BA0",
      500: "#1E293B",
      600: "#0F172A",
      700: "#0B1220",
      800: "#0B1220",
      900: "#0B1220",
    },
  },
  fonts: {
    heading: FONT,
    body: FONT,
  },
  radii: {
    sm: "6px",
    md: "8px",
    lg: "12px",
    xl: "16px",
  },
  shadows: {
    outline: FOCUS_RING,
    xs: "0 1px 2px rgba(15, 23, 42, 0.06)",
  },
  components: {
    Heading: {
      baseStyle: {
        color: "ink.800",
        fontWeight: "700",
        letterSpacing: "-0.03em",
        lineHeight: "1.25",
      },
    },
    Text: {
      baseStyle: {
        color: "ink.700",
        letterSpacing: "-0.01em",
      },
    },
    Button: {
      defaultProps: {
        colorScheme: "ink",
      },
      baseStyle: {
        fontWeight: "600",
        borderRadius: "md",
        letterSpacing: "-0.01em",
      },
      variants: {
        solid: (props: { colorScheme?: string }) => buttonSolid(props.colorScheme),
        outline: (props: { colorScheme?: string }) => buttonOutline(props.colorScheme),
        ghost: (props: { colorScheme?: string }) => {
          const c = props.colorScheme ?? "ink";
          if (GHOST_SEMANTIC.has(c)) {
            return {
              color: `${c}.600`,
              _hover: { bg: `${c}.50` },
              _active: { bg: `${c}.100` },
            };
          }
          return {
            color: "ink.700",
            _hover: { bg: "ink.50" },
            _active: { bg: "ink.100" },
          };
        },
      },
    },
    Tabs: {
      defaultProps: {
        colorScheme: "blue",
      },
      variants: {
        enclosed: {
          root: {
            width: "100%",
          },
          tablist: {
            width: "100%",
            mb: 0,
            borderBottom: "1px solid",
            borderColor: "ink.200",
          },
          tab: {
            mb: 0,
            border: "1px solid",
            borderColor: "transparent",
            borderBottom: "none",
            borderTopRadius: "md",
            _selected: {
              color: "blue.600",
              bg: "white",
              borderColor: "ink.200",
              borderBottomColor: "white",
              mb: "-1px",
            },
          },
          tabpanel: {
            p: 0,
            pt: 6,
          },
        },
      },
    },
    Checkbox: {
      defaultProps: {
        colorScheme: "blue",
      },
    },
    Radio: {
      defaultProps: {
        colorScheme: "blue",
      },
    },
    Progress: {
      defaultProps: {
        colorScheme: "blue",
      },
    },
    Badge: {
      baseStyle: {
        fontWeight: "600",
        letterSpacing: "0.02em",
      },
    },
    Breadcrumb: {
      baseStyle: {
        link: {
          _focusVisible: {
            boxShadow: FOCUS_RING,
            borderRadius: "sm",
          },
        },
      },
    },
    Select: {
      defaultProps: {
        size: "md",
        variant: "outline",
      },
      baseStyle: {
        field: {
          color: "ink.800",
          bg: "white",
          borderColor: "ink.200",
          borderRadius: "md",
          _placeholder: {
            color: "ink.400",
          },
          _focus: {
            borderColor: "blue.500",
            boxShadow: FOCUS_RING,
          },
          _readOnly: {
            bg: "ink.50",
            borderColor: "ink.200",
            cursor: "default",
          },
          _disabled: {
            bg: "ink.50",
            color: "ink.500",
          },
        },
      },
    },
    Input: {
      defaultProps: {
        size: "md",
        variant: "outline",
      },
      baseStyle: {
        field: {
          color: "ink.800",
          bg: "white",
          borderColor: "ink.200",
          borderRadius: "md",
          _placeholder: {
            color: "ink.400",
          },
          _focus: {
            borderColor: "blue.500",
            boxShadow: FOCUS_RING,
          },
          _readOnly: {
            bg: "ink.50",
            borderColor: "ink.200",
            cursor: "default",
          },
          _disabled: {
            bg: "ink.50",
            color: "ink.500",
          },
        },
      },
    },
    Textarea: {
      defaultProps: {
        size: "md",
        variant: "outline",
      },
      baseStyle: {
        color: "ink.800",
        bg: "white",
        borderColor: "ink.200",
        borderRadius: "md",
        _placeholder: {
          color: "ink.400",
        },
        _focus: {
          borderColor: "blue.500",
          boxShadow: FOCUS_RING,
        },
        _readOnly: {
          bg: "ink.50",
          borderColor: "ink.200",
          cursor: "default",
        },
      },
    },
    FormLabel: {
      baseStyle: {
        fontWeight: "600",
        color: "ink.700",
        mb: 1.5,
        letterSpacing: "-0.01em",
        requiredIndicator: {
          color: "red.500",
          ml: "2px",
        },
      },
    },
    Modal: {
      baseStyle: {
        overlay: {
          bg: "blackAlpha.600",
        },
        content: {
          borderRadius: "lg",
          border: "1px solid",
          borderColor: "ink.200",
        },
        header: {
          fontWeight: "700",
          color: "ink.800",
          pb: 3,
          letterSpacing: "-0.02em",
        },
        footer: {
          pt: 2,
          gap: 3,
        },
        body: {
          pt: 2,
        },
      },
    },
    Card: {
      baseStyle: {
        container: {
          bg: "white",
          borderColor: "ink.200",
          borderRadius: "lg",
          boxShadow: "xs",
          transition: "border-color 0.15s ease, box-shadow 0.15s ease",
          _hover: {
            borderColor: "ink.300",
            boxShadow: "sm",
          },
        },
      },
    },
    FormHelperText: {
      baseStyle: {
        fontSize: "xs",
        color: "ink.500",
        mt: 1,
        lineHeight: "1.45",
      },
    },
    FormErrorMessage: {
      baseStyle: {
        fontSize: "xs",
        mt: 1,
        lineHeight: "1.4",
      },
    },
    Table: {
      variants: {
        simple: {
          th: {
            fontSize: "11.5px",
            letterSpacing: "0.05em",
            textTransform: "uppercase",
            color: "ink.500",
            fontWeight: "600",
            borderColor: "ink.200",
            bg: "ink.50",
          },
          td: {
            fontSize: "sm",
            color: "ink.700",
            borderColor: "ink.200",
          },
        },
      },
      defaultProps: {
        variant: "simple",
        size: "sm",
      },
    },
    CloseButton: {
      baseStyle: {
        _focus: {
          boxShadow: "none",
        },
        _focusVisible: {
          boxShadow: "outline",
        },
      },
    },
    Tooltip: {
      baseStyle: {
        fontSize: "xs",
        borderRadius: "md",
        bg: "ink.800",
        color: "white",
        px: 2,
        py: 1,
      },
    },
    Tag: {
      defaultProps: {
        colorScheme: "ink",
      },
    },
    Menu: {
      baseStyle: {
        list: {
          borderColor: "ink.200",
          borderRadius: "md",
          boxShadow: "md",
          py: 1,
        },
        item: {
          fontSize: "sm",
          color: "ink.700",
          _hover: { bg: "ink.50" },
          _focus: { bg: "ink.50" },
        },
      },
    },
    Alert: {
      baseStyle: {
        container: {
          borderRadius: "md",
        },
        title: {
          fontWeight: "600",
        },
      },
      variants: {
        subtle: (props: { status?: string }) => {
          const p = alertPalette(props.status);
          return {
            container: { bg: p.bg, color: p.fg },
            icon: { color: p.accent },
            title: { color: p.fg },
            description: { color: p.fg },
          };
        },
        "left-accent": (props: { status?: string }) => {
          const p = alertPalette(props.status);
          return {
            container: {
              bg: p.bg,
              color: p.fg,
              borderLeft: "3px solid",
              borderColor: p.accent,
            },
            icon: { color: p.accent },
            title: { color: p.fg },
            description: { color: p.fg },
          };
        },
        solid: (props: { status?: string }) => {
          const p = alertPalette(props.status);
          return {
            container: { bg: p.accent, color: "white" },
            icon: { color: "white" },
            title: { color: "white" },
            description: { color: "white" },
          };
        },
      },
      defaultProps: {
        variant: "subtle",
      },
    },
    Spinner: {
      defaultProps: {
        color: "blue.600",
        emptyColor: "ink.100",
      },
    },
  },
  styles: {
    global: {
      body: {
        bg: "light.100",
        color: "ink.700",
        fontFeatureSettings: '"ss01"',
      },
      a: {
        color: "blue.600",
        _hover: {
          textDecoration: "underline",
        },
      },
    },
  },
});

export default customTheme;
