import type { Config } from "tailwindcss";

/**
 * LEDGER design tokens.
 *
 * The default Tailwind palette is intentionally REPLACED, not extended: an
 * unknown utility such as `bg-gray-100` or `text-blue-600` must fail loudly
 * rather than quietly render a default-theme color. Semantic status tokens are
 * desaturated; the single accent is reserved for primary actions and links.
 *
 * Shadow and radius scales are also constrained: this is a dense operations
 * tool where regions are separated by 1px borders, not shadows. `shadow-overlay`
 * is the only shadow, and it exists solely for real overlays (menus, dialogs).
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    // Replaces the default palette. Only these colors exist.
    colors: {
      transparent: "transparent",
      current: "currentColor",
      inherit: "inherit",
      white: "#ffffff",
      black: "#0a0c0f",

      ink: {
        DEFAULT: "#14181c",
        muted: "#565e66",
        subtle: "#7b838b",
        inverted: "#f7f8f9",
      },
      surface: {
        DEFAULT: "#ffffff",
        muted: "#f7f8f9",
        sunken: "#f1f3f4",
      },
      line: {
        DEFAULT: "#e2e5e9",
        strong: "#c9ced4",
        subtle: "#eef0f2",
      },
      accent: {
        DEFAULT: "#1f4ed4",
        hover: "#1a41b0",
        subtle: "#eef2fd",
        border: "#c3d1f5",
      },
      // Semantic status. Every status is a fg/bg/border triplet used by the
      // StatusPill and by the left-border row accent.
      status: {
        matched: { DEFAULT: "#1c6b45", bg: "#e9f3ed", border: "#bcdccb" },
        review: { DEFAULT: "#7d5407", bg: "#faf3e3", border: "#e8d6a8" },
        discrepancy: { DEFAULT: "#96271f", bg: "#fbeeec", border: "#eac6c2" },
        pending: { DEFAULT: "#555d65", bg: "#eef0f2", border: "#d5d9dd" },
      },
    },
    borderColor: ({ theme }) => ({
      DEFAULT: theme("colors.line.DEFAULT"),
      ...theme("colors"),
    }),
    divideColor: ({ theme }) => ({
      DEFAULT: theme("colors.line.DEFAULT"),
      ...theme("colors"),
    }),
    outlineColor: ({ theme }) => ({
      DEFAULT: theme("colors.accent.DEFAULT"),
      ...theme("colors"),
    }),
    ringColor: ({ theme }) => ({
      DEFAULT: theme("colors.accent.DEFAULT"),
      ...theme("colors"),
    }),
    ringOffsetColor: ({ theme }) => ({
      ...theme("colors"),
    }),
    fontFamily: {
      sans: [
        "system-ui",
        "-apple-system",
        "Segoe UI",
        "Roboto",
        "Helvetica Neue",
        "Arial",
        "sans-serif",
      ],
      mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "Liberation Mono", "monospace"],
    },
    borderRadius: {
      none: "0",
      sm: "2px",
      DEFAULT: "4px",
      control: "4px",
      md: "6px",
      panel: "6px",
      full: "9999px",
    },
    boxShadow: {
      none: "none",
      overlay: "0 8px 24px rgba(10, 12, 15, 0.12)",
    },
    extend: {
      fontSize: {
        // Dense table/toolbar type scale.
        "2xs": ["11px", { lineHeight: "16px" }],
      },
      spacing: {
        // Nothing arbitrary: 4/8px grid only.
      },
    },
  },
  plugins: [],
};

export default config;
