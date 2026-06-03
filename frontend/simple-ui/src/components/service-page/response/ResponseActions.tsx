// Copy, download, and export actions for service responses

import React from "react";
import { Button, HStack } from "@chakra-ui/react";
import { FaCopy, FaDownload, FaFileExport } from "react-icons/fa";
import type { ResponseActionConfig, ResponseActionKind } from "../../../types/servicePage";

export interface ResponseActionsProps {
  actions: ResponseActionConfig[];
}

const iconForKind = (kind?: ResponseActionKind) => {
  switch (kind) {
    case "copy":
      return <FaCopy />;
    case "download":
      return <FaDownload />;
    case "export":
      return <FaFileExport />;
    default:
      return undefined;
  }
};

const ResponseActions: React.FC<ResponseActionsProps> = ({ actions }) => {
  const visible = actions.filter((a) => a.visible !== false);
  if (!visible.length) return null;

  return (
    <HStack spacing={4} w="full" justify="center" flexWrap="wrap">
      {visible.map((action) => (
        <Button
          key={action.id}
          leftIcon={iconForKind(action.kind)}
          size="sm"
          variant="outline"
          onClick={action.onClick}
        >
          {action.label}
        </Button>
      ))}
    </HStack>
  );
};

export default ResponseActions;
