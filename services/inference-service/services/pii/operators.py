"""Custom Presidio operator that produces numbered, reusable tokens.

Adapted from Presidio's pseudonymization sample notebook
(docs/samples/python/pseudonomyzation.ipynb in the Presidio repo).
This class is NOT part of the presidio-anonymizer package; it is built on
Presidio's Operator base class and registered on the AnonymizerEngine.
"""

from typing import Dict

from presidio_anonymizer.operators import Operator, OperatorType

OPERATOR_NAME = "entity_counter"
TOKEN_FORMAT = "<{entity_type}_{index}>"


class InstanceCounterAnonymizer(Operator):
    """Replaces each PII value with <ENTITY_TYPE_N>.

    - Separate counter per entity type (<PERSON_1>, <EMAIL_ADDRESS_1>).
    - Same value -> same token (Alice is always <PERSON_1>).
    - Numbering starts at 1.

    Presidio calls this operator once per entity, AFTER it has resolved
    overlapping/duplicate detections and merged adjacent same-type entities.
    Presidio processes entities right to left, so within one text the
    numbers can look reversed. That is harmless: tokens are only IDs.
    """

    def operate(self, text: str, params: Dict = None) -> str:
        entity_type: str = params["entity_type"]  # injected by Presidio
        entity_mapping: Dict[str, Dict[str, str]] = params["entity_mapping"]

        per_type = entity_mapping.setdefault(entity_type, {})
        if text not in per_type:
            per_type[text] = TOKEN_FORMAT.format(
                entity_type=entity_type, index=len(per_type) + 1
            )
        return per_type[text]

    def validate(self, params: Dict = None) -> None:
        # entity_type is not checked here: presidio-anonymizer 2.2.35 calls
        # validate() before injecting it into params (operate() always has it).
        if not params or "entity_mapping" not in params:
            raise ValueError("An input dict called `entity_mapping` is required.")

    def operator_name(self) -> str:
        return OPERATOR_NAME

    def operator_type(self) -> OperatorType:
        return OperatorType.Anonymize
