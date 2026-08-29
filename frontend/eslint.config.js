import { readdirSync } from 'node:fs'
import path from 'node:path'
import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import importPlugin from 'eslint-plugin-import'
import tseslint from 'typescript-eslint'

// Read from disk, never hand-listed: a literal list drifts silently both ways.
// A feature missing from it is simply unguarded, and a zone naming a folder that
// no longer exists matches nothing. Neither failure raises an error.
const FEATURES = readdirSync(path.join(import.meta.dirname, 'src/features'), {
  withFileTypes: true,
})
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name)

// Shared layers: every feature may import them, they may import no feature back.
// `plan` is one because a plan item is rendered on more than one surface (trip/
// today), so the cross-feature import is the design, not a leak. Lifting it into
// components/ would strip it of the api and mutation code it needs.
const SHARED_FEATURES = ['plan']

// The one list still written by hand, so it fails loudly rather than quietly
// granting an exception to a folder that no longer exists.
for (const shared of SHARED_FEATURES) {
  if (!FEATURES.includes(shared)) {
    throw new Error(`SHARED_FEATURES names src/features/${shared}, which is gone.`)
  }
}

export default tseslint.config(
  {
    ignores: [
      'dist',
      'dev-dist',
      'src/routeTree.gen.ts',
      'src/api/schema.d.ts',
    ],
  },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
      import: importPlugin,
    },
    settings: {
      'import/resolver': {
        // Without this the zones below are inert: no-restricted-paths skips any
        // import it cannot resolve, the node resolver knows nothing about the
        // "@/" alias, and every cross-layer import in src/ is written with it.
        // The mapping stays in tsconfig.app.json rather than being repeated here.
        typescript: {
          project: path.join(import.meta.dirname, 'tsconfig.app.json'),
        },
        node: { extensions: ['.ts', '.tsx'] },
      },
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],
      // Import boundaries (FRONTEND_IMPLEMENTATION_PLAN.md section 8): the
      // architecture lives in these rules, not in folder names.
      'import/no-restricted-paths': [
        'error',
        {
          zones: [
            // Primitives are leaf nodes: no reaching up into app code.
            {
              target: './src/components',
              from: ['./src/features', './src/routes', './src/app'],
              message: 'components/ui are presentational primitives; they never import application layers.',
            },
            // The one sanctioned api import for primitives is the generated
            // contract types (StatusBadge switches over generated enums).
            {
              target: './src/components',
              from: './src/api',
              except: ['./schema.d.ts'],
              message: 'components/ui may import generated contract types only, never the client or hooks.',
            },
            // Features compose primitives and api; routes/app compose features, never the reverse.
            {
              target: './src/features',
              from: ['./src/routes', './src/app'],
              message: 'features must not import routes/ or app/; the dependency points the other way.',
            },
            // No cross-feature imports; shared code moves to components/, lib/,
            // api/, or a declared shared feature. A shared feature gets no
            // exception of its own beyond itself, which is what keeps it a leaf.
            ...FEATURES.map((feature) => ({
              target: `./src/features/${feature}`,
              from: './src/features',
              except: [
                ...new Set([
                  `./${feature}`,
                  ...(SHARED_FEATURES.includes(feature)
                    ? []
                    : SHARED_FEATURES.map((shared) => `./${shared}`)),
                ]),
              ],
              message: `features must not import each other; lift shared code into components/, lib/, api/, or a shared feature (${SHARED_FEATURES.join(', ')}).`,
            })),
            // Test-scoped mocks never reach the production bundle.
            {
              target: [
                './src/app',
                './src/routes',
                './src/features',
                './src/components',
                './src/api',
                './src/lib',
                './src/styles',
              ],
              from: './src/test',
              message: 'src/test (setup + contract-generated mocks) is test-scoped and never bundled.',
            },
          ],
        },
      ],
    },
  },
  {
    // Design tokens are defined once in src/styles; everywhere else, color
    // literals are a smell that bypasses the token system.
    files: ['src/**/*.{ts,tsx}'],
    ignores: ['src/styles/**'],
    rules: {
      'no-restricted-syntax': [
        'error',
        {
          selector: 'Literal[value=/^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/]',
          message: 'Hex colors live in src/styles/tokens.css (and its TS mirror) only.',
        },
      ],
    },
  },
)
