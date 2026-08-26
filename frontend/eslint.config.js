import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import importPlugin from 'eslint-plugin-import'
import tseslint from 'typescript-eslint'

const FEATURES = [
  'onboarding',
  'today',
  'trip',
  'explore',
  'agent',
  'actions',
  'notifications',
]

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
            // No cross-feature imports; shared code moves to components/, lib/, or api/.
            ...FEATURES.map((feature) => ({
              target: `./src/features/${feature}`,
              from: './src/features',
              except: [`./${feature}`],
              message: 'features must not import each other; lift shared code into components/, lib/, or api/.',
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
