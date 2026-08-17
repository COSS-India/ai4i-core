/// <reference types="jest" />

import { stripJsonComments } from "../../src/utils/stripJsonComments";

const parse = (jsonc: string) => JSON.parse(stripJsonComments(jsonc));

describe("stripJsonComments", () => {
  it("removes line comments, whether trailing or on their own line", () => {
    expect(
      parse(`{
        // leading comment
        "a": 1, // trailing comment
        "b": 2
      }`)
    ).toEqual({ a: 1, b: 2 });
  });

  it("removes block comments", () => {
    expect(parse('{/* hi */ "a": 1 /* there */ }')).toEqual({ a: 1 });
  });

  it("preserves comment markers inside string values", () => {
    expect(parse('{"refUrl": "https://github.com/example/model"}')).toEqual({
      refUrl: "https://github.com/example/model",
    });
    expect(parse('{"a": "/* not a block comment */"}')).toEqual({
      a: "/* not a block comment */",
    });
  });

  it("preserves escaped quotes so strings are not ended early", () => {
    expect(parse('{"a": "say \\"hi\\" // not a comment"}')).toEqual({
      a: 'say "hi" // not a comment',
    });
  });

  it("drops trailing commas left behind when a field is commented out", () => {
    expect(
      parse(`{
        "a": 1,
        "b": 2,
        // "c": 3
      }`)
    ).toEqual({ a: 1, b: 2 });

    expect(parse('{"a": [1, 2, // note\n]}')).toEqual({ a: [1, 2] });
  });

  it("leaves comment-free JSON unchanged", () => {
    const json = '{"a":1,"b":[1,2],"c":{"d":"e"}}';
    expect(stripJsonComments(json)).toBe(json);
  });

  it("parses the annotated sample-model shape end to end", () => {
    const sample = `{
      // ── Identity ──
      "version": "v1",
      // Required. Version for the model. 1–20 characters.

      "refUrl": "https://github.com/example/example-model",
      // Optional. GitHub link giving further info.

      "task": {
        "type": "llm"
        // Enum — one of: nmt | tts | asr | llm
      },
      "domain": ["general"],
      "asyncApiDetails": null
      // Required when isSyncApi is false.
    }`;

    expect(parse(sample)).toEqual({
      version: "v1",
      refUrl: "https://github.com/example/example-model",
      task: { type: "llm" },
      domain: ["general"],
      asyncApiDetails: null,
    });
  });
});
