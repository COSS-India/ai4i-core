"""Triton-level stub responses for the NER service.

These mirror the raw JSON that Triton's KServe v2 endpoint returns for a NER
infer call.  Each element in ``outputs[0].data`` is a JSON string containing
``source`` and ``nerPrediction`` fields.

Three sizes based on input text character length:
  SMALL_NER_TRITON_RESPONSE   — short phrase, 2 entities
  MEDIUM_NER_TRITON_RESPONSE  — two sentences, 6 entities
  LARGE_NER_TRITON_RESPONSE   — full paragraph, 12+ entities
"""

import json
from typing import Any

SMALL_NER_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "ner",
    "model_version": "1",
    "outputs": [
        {
            "name": "OUTPUT_TEXT",
            "datatype": "BYTES",
            "shape": [1, 1],
            "data": [
                json.dumps({
                    "source": "John visited Paris.",
                    "nerPrediction": [
                        {"token": "John",    "tag": "PER", "tokenIndex": 0, "tokenStartIndex": 0,  "tokenEndIndex": 4},
                        {"token": "visited", "tag": "O",   "tokenIndex": 1, "tokenStartIndex": 5,  "tokenEndIndex": 12},
                        {"token": "Paris.",  "tag": "LOC", "tokenIndex": 2, "tokenStartIndex": 13, "tokenEndIndex": 19},
                    ],
                })
            ],
        }
    ],
}

MEDIUM_NER_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "ner",
    "model_version": "1",
    "outputs": [
        {
            "name": "OUTPUT_TEXT",
            "datatype": "BYTES",
            "shape": [1, 1],
            "data": [
                json.dumps({
                    "source": "John Smith joined Google in New York last Tuesday. He will report to Sarah Connor at the Mountain View office.",
                    "nerPrediction": [
                        {"token": "John",     "tag": "PER",  "tokenIndex": 0,  "tokenStartIndex": 0,   "tokenEndIndex": 4},
                        {"token": "Smith",    "tag": "PER",  "tokenIndex": 1,  "tokenStartIndex": 5,   "tokenEndIndex": 10},
                        {"token": "Google",   "tag": "ORG",  "tokenIndex": 3,  "tokenStartIndex": 18,  "tokenEndIndex": 24},
                        {"token": "New",      "tag": "LOC",  "tokenIndex": 5,  "tokenStartIndex": 28,  "tokenEndIndex": 31},
                        {"token": "York",     "tag": "LOC",  "tokenIndex": 6,  "tokenStartIndex": 32,  "tokenEndIndex": 36},
                        {"token": "Tuesday.", "tag": "DATE", "tokenIndex": 8,  "tokenStartIndex": 42,  "tokenEndIndex": 50},
                        {"token": "Sarah",    "tag": "PER",  "tokenIndex": 13, "tokenStartIndex": 69,  "tokenEndIndex": 74},
                        {"token": "Connor",   "tag": "PER",  "tokenIndex": 14, "tokenStartIndex": 75,  "tokenEndIndex": 81},
                        {"token": "Mountain", "tag": "LOC",  "tokenIndex": 17, "tokenStartIndex": 89,  "tokenEndIndex": 97},
                        {"token": "View",     "tag": "LOC",  "tokenIndex": 18, "tokenStartIndex": 98,  "tokenEndIndex": 102},
                    ],
                })
            ],
        }
    ],
}

LARGE_NER_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "ner",
    "model_version": "1",
    "outputs": [
        {
            "name": "OUTPUT_TEXT",
            "datatype": "BYTES",
            "shape": [1, 1],
            "data": [
                json.dumps({
                    "source": (
                        "Dr. Emily Watson of Harvard University published a landmark study on climate change "
                        "with funding from the United Nations Environment Programme and the World Bank. "
                        "The research was conducted in collaboration with Professor Arun Mehta at IIT Delhi "
                        "and Dr. Lena Fischer at the Max Planck Institute in Berlin, Germany. "
                        "The findings were presented at COP28 in Dubai, UAE on December 12, 2023. "
                        "Amazon, Microsoft, and Google pledged over $500 million to support the initiative."
                    ),
                    "nerPrediction": [
                        {"token": "Dr.",         "tag": "PER",  "tokenIndex": 0,  "tokenStartIndex": 0,   "tokenEndIndex": 3},
                        {"token": "Emily",       "tag": "PER",  "tokenIndex": 1,  "tokenStartIndex": 4,   "tokenEndIndex": 9},
                        {"token": "Watson",      "tag": "PER",  "tokenIndex": 2,  "tokenStartIndex": 10,  "tokenEndIndex": 16},
                        {"token": "Harvard",     "tag": "ORG",  "tokenIndex": 4,  "tokenStartIndex": 20,  "tokenEndIndex": 27},
                        {"token": "University",  "tag": "ORG",  "tokenIndex": 5,  "tokenStartIndex": 28,  "tokenEndIndex": 38},
                        {"token": "United",      "tag": "ORG",  "tokenIndex": 6,  "tokenStartIndex": 74,  "tokenEndIndex": 80},
                        {"token": "Nations",     "tag": "ORG",  "tokenIndex": 7,  "tokenStartIndex": 81,  "tokenEndIndex": 88},
                        {"token": "World",       "tag": "ORG",  "tokenIndex": 10, "tokenStartIndex": 119, "tokenEndIndex": 124},
                        {"token": "Bank.",       "tag": "ORG",  "tokenIndex": 11, "tokenStartIndex": 125, "tokenEndIndex": 130},
                        {"token": "Arun",        "tag": "PER",  "tokenIndex": 13, "tokenStartIndex": 173, "tokenEndIndex": 177},
                        {"token": "Mehta",       "tag": "PER",  "tokenIndex": 14, "tokenStartIndex": 178, "tokenEndIndex": 183},
                        {"token": "IIT",         "tag": "ORG",  "tokenIndex": 15, "tokenStartIndex": 187, "tokenEndIndex": 190},
                        {"token": "Delhi",       "tag": "ORG",  "tokenIndex": 16, "tokenStartIndex": 191, "tokenEndIndex": 196},
                        {"token": "Lena",        "tag": "PER",  "tokenIndex": 18, "tokenStartIndex": 205, "tokenEndIndex": 209},
                        {"token": "Fischer",     "tag": "PER",  "tokenIndex": 19, "tokenStartIndex": 210, "tokenEndIndex": 217},
                        {"token": "Max",         "tag": "ORG",  "tokenIndex": 20, "tokenStartIndex": 225, "tokenEndIndex": 228},
                        {"token": "Planck",      "tag": "ORG",  "tokenIndex": 21, "tokenStartIndex": 229, "tokenEndIndex": 235},
                        {"token": "Berlin,",     "tag": "LOC",  "tokenIndex": 23, "tokenStartIndex": 249, "tokenEndIndex": 256},
                        {"token": "Germany.",    "tag": "LOC",  "tokenIndex": 24, "tokenStartIndex": 257, "tokenEndIndex": 265},
                        {"token": "Dubai,",      "tag": "LOC",  "tokenIndex": 26, "tokenStartIndex": 310, "tokenEndIndex": 316},
                        {"token": "UAE",         "tag": "LOC",  "tokenIndex": 27, "tokenStartIndex": 317, "tokenEndIndex": 320},
                        {"token": "December",    "tag": "DATE", "tokenIndex": 28, "tokenStartIndex": 324, "tokenEndIndex": 332},
                        {"token": "2023.",       "tag": "DATE", "tokenIndex": 30, "tokenStartIndex": 337, "tokenEndIndex": 342},
                        {"token": "Amazon,",     "tag": "ORG",  "tokenIndex": 31, "tokenStartIndex": 343, "tokenEndIndex": 350},
                        {"token": "Microsoft,",  "tag": "ORG",  "tokenIndex": 32, "tokenStartIndex": 351, "tokenEndIndex": 361},
                        {"token": "Google",      "tag": "ORG",  "tokenIndex": 33, "tokenStartIndex": 366, "tokenEndIndex": 372},
                    ],
                })
            ],
        }
    ],
}
