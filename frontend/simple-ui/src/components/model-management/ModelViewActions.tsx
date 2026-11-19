import { Badge, Box, HStack, Switch, Tooltip } from "@chakra-ui/react";
import React from "react";
import CreateButton from "../common/CreateButton";

type ModelViewActionsProps = {
  isReadOnly: boolean;
  /** Service counts loaded without error; the status switch waits for them. */
  serviceCountsReady: boolean;
  isActive: boolean;
  isDeprecated: boolean;
  hasLinkedServices: boolean;
  /** BE rejects deprecate with 409 while a service is published. */
  hasPublishedService: boolean;
  isUpdating: boolean;
  onCreateService: () => void;
  onActivate: () => void;
  onDeprecate: () => void;
};

function ActivateSwitch({
  isUpdating,
  onActivate,
}: Readonly<Pick<ModelViewActionsProps, "isUpdating" | "onActivate">>) {
  return (
    <Tooltip label="Activate model" placement="top" hasArrow>
      <Box as="span" display="inline-flex" alignItems="center">
        <Switch
          size="md"
          colorScheme="green"
          isChecked={false}
          onChange={onActivate}
          isDisabled={isUpdating}
        />
      </Box>
    </Tooltip>
  );
}

function DeprecateSwitch({
  isUpdating,
  hasPublishedService,
  onDeprecate,
}: Readonly<
  Pick<ModelViewActionsProps, "isUpdating" | "hasPublishedService" | "onDeprecate">
>) {
  return (
    <Tooltip
      label={
        hasPublishedService ? "Unpublish its services to deprecate" : "Deprecate model"
      }
      placement="top"
      hasArrow
    >
      <Box as="span" display="inline-flex" alignItems="center">
        <Switch
          size="md"
          colorScheme="green"
          isChecked={true}
          onChange={() => {
            if (hasPublishedService) return;
            onDeprecate();
          }}
          isDisabled={isUpdating || hasPublishedService}
        />
      </Box>
    </Tooltip>
  );
}

/** Deprecated → activate; active with services → deprecate; otherwise nothing. */
function statusSwitch(props: Readonly<ModelViewActionsProps>): React.ReactNode {
  if (props.isReadOnly || !props.serviceCountsReady) return null;
  if (props.isDeprecated) return <ActivateSwitch {...props} />;
  if (props.isActive && props.hasLinkedServices) return <DeprecateSwitch {...props} />;
  return null;
}

/** Header actions of the model view drawer: read-only badge, Create Service, status switch. */
const ModelViewActions: React.FC<Readonly<ModelViewActionsProps>> = (props) => (
  <HStack spacing={2}>
    {props.isReadOnly ? (
      <Badge colorScheme="gray" fontSize="xs" px={2} py={0.5}>
        Read-only
      </Badge>
    ) : null}
    {!props.isReadOnly && props.isActive ? (
      <CreateButton size="sm" onClick={props.onCreateService}>
        Create Service
      </CreateButton>
    ) : null}
    {statusSwitch(props)}
  </HStack>
);

export default ModelViewActions;
