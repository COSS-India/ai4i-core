import { extendTheme } from "@chakra-ui/react";

const customTheme = extendTheme({
  colors: {
    primary: {
      50: "#fff7ed",
      100: "#ffedd5",
      200: "#fed7aa",
      300: "#fdba74",
      400: "#fb923c",
      500: "#f97316",
      600: "#ea580c",
      700: "#c2410c",
      800: "#9a3412",
      900: "#7c2d12",
    },
    light: {
      100: "#F7FAFC",
      200: "#FFFFFF",
    },
    dark: {
      100: "#1A202C",
      200: "#2D3748",
    },
  },
  fonts: {
    heading: "Inter, sans-serif",
    body: "Inter, sans-serif",
  },
  components: {
    Button: {
      defaultProps: {
        colorScheme: "orange",
      },
      baseStyle: {
        fontWeight: "medium",
        borderRadius: "md",
      },
    },
    Select: {
      defaultProps: {
        size: "md",
        variant: "outline",
      },
      baseStyle: {
        field: {
          color: "gray.800",
          bg: "white",
          borderColor: "gray.300",
          borderRadius: "md",
          _placeholder: {
            color: "gray.500",
          },
          _focus: {
            borderColor: "orange.500",
            boxShadow: "0 0 0 1px orange.500",
          },
          _readOnly: {
            bg: "gray.50",
            borderColor: "gray.200",
            cursor: "default",
          },
          _disabled: {
            bg: "gray.50",
            color: "gray.500",
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
          color: "gray.800",
          bg: "white",
          borderColor: "gray.300",
          borderRadius: "md",
          _placeholder: {
            color: "gray.500",
          },
          _focus: {
            borderColor: "orange.500",
            boxShadow: "0 0 0 1px orange.500",
          },
          _readOnly: {
            bg: "gray.50",
            borderColor: "gray.200",
            cursor: "default",
          },
          _disabled: {
            bg: "gray.50",
            color: "gray.500",
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
        color: "gray.800",
        bg: "white",
        borderColor: "gray.300",
        borderRadius: "md",
        _placeholder: {
          color: "gray.500",
        },
        _focus: {
          borderColor: "orange.500",
          boxShadow: "0 0 0 1px orange.500",
        },
        _readOnly: {
          bg: "gray.50",
          borderColor: "gray.200",
          cursor: "default",
        },
      },
    },
    FormLabel: {
      baseStyle: {
        fontWeight: "semibold",
        color: "gray.700",
        mb: 1.5,
      },
    },
    Modal: {
      baseStyle: {
        overlay: {
          bg: "blackAlpha.600",
        },
        content: {
          borderRadius: "lg",
        },
        header: {
          fontWeight: "semibold",
          color: "gray.800",
          pb: 3,
        },
        body: {
          pt: 2,
        },
      },
    },
  },
  styles: {
    global: {
      body: {
        bg: "light.100",
        color: "gray.800",
      },
      a: {
        _hover: {
          textDecoration: "underline",
        },
      },
    },
  },
});

export default customTheme;
