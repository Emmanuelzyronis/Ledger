import { describe, expect, it } from "vitest";

import config from "../tailwind.config";

import { readSources } from "./support/read";

type Theme = NonNullable<typeof config.theme>;
const theme = config.theme as Theme;

describe("design tokens are defined in config, not scattered in components", () => {
  it("replaces the default Tailwind palette instead of extending it", () => {
    expect(theme.colors).toBeTruthy();
    expect(theme.extend?.colors).toBeUndefined();
  });

  it("defines the neutral base, one accent, and the four semantic status tones", () => {
    const colors = theme.colors as Record<string, unknown>;
    for (const token of ["ink", "surface", "line", "accent", "status", "white"]) {
      expect(Object.keys(colors)).toContain(token);
    }
    const status = colors.status as Record<string, Record<string, string>>;
    expect(Object.keys(status).sort()).toEqual(["discrepancy", "matched", "pending", "review"]);
    for (const tone of Object.values(status)) {
      expect(Object.keys(tone).sort()).toEqual(["DEFAULT", "bg", "border"]);
    }
    const accent = colors.accent as Record<string, string>;
    expect(Object.keys(accent).sort()).toEqual(["DEFAULT", "border", "hover", "subtle"]);
  });

  it("caps data-container radius at 6px and keeps shadows for overlays only", () => {
    const radius = theme.borderRadius as Record<string, string>;
    for (const forbidden of ["lg", "xl", "2xl", "3xl"]) {
      expect(Object.keys(radius)).not.toContain(forbidden);
    }
    expect(radius.panel).toBe("6px");

    const shadows = theme.boxShadow as Record<string, string>;
    for (const [name, value] of Object.entries(shadows)) {
      if (name === "overlay") continue;
      expect(value).toBe("none");
    }
    expect(shadows.overlay).toBeTruthy();
  });
});

const FORBIDDEN_CLASS_PATTERNS: readonly { name: string; pattern: RegExp }[] = [
  { name: "gradient", pattern: /(^|[^\w-])bg-(gradient|linear)/ },
  { name: "backdrop blur", pattern: /backdrop-blur/ },
  { name: "drop shadow", pattern: /(^|[^\w-])drop-shadow/ },
  { name: "blur", pattern: /(^|[^\w-])blur-(sm|md|lg|xl|2xl|3xl)/ },
  { name: "glow", pattern: /glow/i },
  { name: "oversized radius", pattern: /rounded(-\w+)?-(lg|xl|2xl|3xl)/ },
  { name: "generic shadow", pattern: /(^|[^\w-])shadow-(sm|md|lg|xl|2xl|inner)/ },
  { name: "animation", pattern: /(^|[^\w-])animate-/ },
  { name: "transition polish", pattern: /(^|[^\w-])(transition|duration-\d|ease-(in|out|linear))/ },
  {
    name: "default palette color",
    pattern:
      /(bg|text|border|from|to|via|ring|divide)-(slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}/,
  },
  { name: "raw hex color in a component", pattern: /#[0-9a-fA-F]{6}\b/ },
  { name: "hero-scale type", pattern: /text-(5xl|6xl|7xl|8xl|9xl)/ },
];

describe("no generic-AI-dashboard styling slips into the app", () => {
  it("contains no forbidden utility class or raw color in src", async () => {
    const violations: string[] = [];
    for (const file of await readSources()) {
      for (const rule of FORBIDDEN_CLASS_PATTERNS) {
        const match = file.text.match(rule.pattern);
        if (match) violations.push(`${file.path}: ${rule.name} -> "${match[0]}"`);
      }
    }
    expect(violations).toEqual([]);
  });

  it("uses tabular figures and monospace for identifiers", async () => {
    const sources = await readSources();
    const combined = sources.map((file) => file.text).join("\n");
    expect(combined).toContain("tabular-nums");
    expect(combined).toContain("font-mono");
  });
});
