import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const config = defineConfig([
  ...nextVitals,
  ...nextTypescript,
  globalIgnores([
    ".next/**",
    "node_modules/**",
    "playwright-report/**",
    "test-results/**",
    "next-env.d.ts",
  ]),
  {
    rules: {
      // Unused arguments are often required by a signature; a leading underscore is the
      // agreed way to say "intentionally ignored".
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      "@typescript-eslint/consistent-type-imports": [
        "error",
        { prefer: "type-imports", fixStyle: "inline-type-imports" },
      ],
      // Tokens and session data must never reach localStorage; cookies are the transport.
      "no-restricted-globals": [
        "error",
        { name: "localStorage", message: "Session data belongs in HttpOnly cookies." },
        { name: "sessionStorage", message: "Session data belongs in HttpOnly cookies." },
      ],
    },
  },
]);

export default config;
