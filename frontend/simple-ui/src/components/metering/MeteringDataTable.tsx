import { Box, Table, TableProps } from "@chakra-ui/react";
import React, { useCallback } from "react";

interface MeteringDataTableProps extends TableProps {
  children: React.ReactNode;
}

/**
 * Shared metering table shell. Truncates cell overflow at the root and shows
 * the full text via native tooltip when the cell content is actually clipped.
 */
const MeteringDataTable: React.FC<MeteringDataTableProps> = ({
  children,
  size = "sm",
  variant = "simple",
  ...tableProps
}) => {
  const onMouseOver = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const cell = (e.target as HTMLElement | null)?.closest?.("td, th") as
      | HTMLTableCellElement
      | null;
    if (!cell) return;
    const overflowed = cell.scrollWidth > cell.clientWidth + 1;
    if (overflowed) {
      const text = (cell.textContent ?? "").trim();
      if (text) cell.setAttribute("title", text);
    } else {
      cell.removeAttribute("title");
    }
  }, []);

  return (
    <Box
      overflowX="auto"
      borderWidth="1px"
      borderColor="gray.200"
      borderRadius="md"
      bg="white"
      onMouseOver={onMouseOver}
    >
      <Table
        size={size}
        variant={variant}
        sx={{
          th: { verticalAlign: "middle" },
          td: {
            verticalAlign: "middle",
            maxW: "280px",
            overflow: "hidden",
            whiteSpace: "nowrap",
            textOverflow: "ellipsis",
          },
        }}
        {...tableProps}
      >
        {children}
      </Table>
    </Box>
  );
};

export default MeteringDataTable;
