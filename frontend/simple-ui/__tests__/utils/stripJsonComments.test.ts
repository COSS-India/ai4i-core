/// <reference types="jest" />

import { SAMPLE_MODEL_JSON } from "../../src/utils/sampleModelJson";
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

  it("removes only the dangling comma, leaving the surrounding layout intact", () => {
    // No dangling comma — the original spacing is left alone
    expect(stripJsonComments('{\n  "a": 1\n}')).toBe('{\n  "a": 1\n}');
    // Dangling comma — the comma goes, but the line breaks after it stay
    expect(stripJsonComments('{\n  "a": 1,\n\n}')).toBe('{\n  "a": 1\n\n}');
  });

  it("handles dangling commas at consecutive closing brackets", () => {
    expect(parse('{"a": {"b": [1, 2, ], }, }')).toEqual({ a: { b: [1, 2] } });
  });

  it("keeps a trailing backslash from swallowing the closing quote", () => {
    expect(parse('{"a": "back\\\\", "b": 1}')).toEqual({ a: "back\\", b: 1 });
  });

  describe("line fidelity", () => {
    const countLines = (text: string) => (text.match(/\n/g) || []).length;

    it.each([
      ["line comments", '{\n  // one\n  // two\n  "a": 1\n}\n'],
      ["a block comment spanning lines", '{\n  /* one\n     two\n     three */\n  "a": 1\n}\n'],
      ["a dangling comma before blank lines", '{\n  "a": 1,\n\n\n  // removed\n}\n'],
      ["comments inside nested structures", '{\n  "a": [\n    1, // one\n    /* two\n       three */\n  ]\n}\n'],
    ])("keeps every line break when stripping %s", (_label, input) => {
      expect(countLines(stripJsonComments(input))).toBe(countLines(input));
    });

    it("reports the line the user actually broke", () => {
      // "b" is missing its comma, on line 5 of the file the user edited
      const edited = `{
  // a comment
  "a": 1,
  /* a block
     comment */
  "b": 2
  "c": 3
}`;
      let reported = "";
      try {
        parse(edited);
      } catch (error) {
        reported = (error as Error).message;
      }

      expect(reported).toContain("line 7");
    });
  });

  it("stays linear on large inputs", () => {
    const entries = Array.from(
      { length: 3500 },
      (_, i) => `    {
      "benchmarkId": "bench-${i}", // an id
      "refUrl": "https://example.com/b/${i}",
      "score": [ { "metricName": "WER", "score": "7.5" } ]
    }`
    );
    const large = `{\n  // header\n  "benchmarks": [\n${entries.join(",\n")}\n  ]\n}`;

    const startedAt = Date.now();
    const parsed = JSON.parse(stripJsonComments(large));
    const elapsed = Date.now() - startedAt;

    expect(parsed.benchmarks).toHaveLength(3500);
    // ~26ms when linear; a quadratic tail-trim takes several seconds at this size
    expect(elapsed).toBeLessThan(2000);
  });

});

describe("SAMPLE_MODEL_JSON", () => {
  it("still carries its explanatory comments for the downloaded file", () => {
    expect(SAMPLE_MODEL_JSON).toContain("// Required. Version for the model.");
    expect(SAMPLE_MODEL_JSON.split("\n").filter((line) => line.includes("//")).length).toBeGreaterThan(50);
  });

  it("parses once the comments are stripped", () => {
    expect(() => parse(SAMPLE_MODEL_JSON)).not.toThrow();
  });

  it("exposes the top-level fields the registration API expects", () => {
    expect(Object.keys(parse(SAMPLE_MODEL_JSON))).toEqual([
      "version",
      "name",
      "description",
      "refUrl",
      "task",
      "languages",
      "isLangDetectionEnabled",
      "isMultilingual",
      "license",
      "licenseUrl",
      "domain",
      "callbackUrl",
      "inferenceApiKey",
      "isSyncApi",
      "asyncApiDetails",
      "adapterConfig",
      "schema",
      "trainingDataset",
      "benchmarks",
      "submitter",
    ]);
  });

  it("keeps URLs and nested structures intact through the strip", () => {
    const sample = parse(SAMPLE_MODEL_JSON);

    expect(sample.refUrl).toBe("https://github.com/example/example-model");
    expect(sample.licenseUrl).toBe("https://opensource.org/licenses/MIT");
    expect(sample.callbackUrl).toBe(
      "https://inference.example.com/v2/models/example-model/infer"
    );
    expect(sample.task).toEqual({ type: "llm" });
    expect(sample.adapterConfig.inputs[0]).toEqual({
      tensor: "INPUT_TEXT",
      dtype: "BYTES",
      shape: [-1, 1],
      value_path: "input.source",
    });
    expect(sample.benchmarks[0].score).toEqual([{ metricName: "WER", score: "7.5" }]);
    expect(sample.submitter.team[0].oauthId.provider).toBe("google");
    expect(sample.asyncApiDetails).toBeNull();
  });
});
