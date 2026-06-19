import { Box, Table, TableProps } from "@chakra-ui/react";
import React from "react";

interface MeteringDataTableProps extends TableProps {
  children: React.ReactNode;
}

const MeteringDataTable: React.FC<MeteringDataTableProps> = ({
  children,
  size = "sm",
  variant = "simple",
  ...tableProps
}) => (
  <Box overflowX="auto" borderWidth="1px" borderColor="gray.200" borderRadius="md" bg="white">
    <Table
      size={size}
      variant={variant}
      sx={{ "th, td": { verticalAlign: "middle" } }}
      {...tableProps}
    >
      {children}
    </Table>
  </Box>
);

export default MeteringDataTable;
