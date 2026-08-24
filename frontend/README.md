# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

## Local and Deployed Backend Integration

TravelWell AI connects to a Python FastAPI backend powered by Google Agent Development Kit (ADK).

### 1. Running locally with local backend
1. Set up the backend `.env` variables (e.g. `GOOGLE_GENAI_USE_VERTEXAI=true` or `GEMINI_API_KEY`).
2. Run backend server:
   ```bash
   cd backend
   python -m uvicorn app.fast_api_app:app --host 0.0.0.0 --port 8000
   ```
3. Set up the frontend configuration:
   Create `frontend/.env` file:
   ```env
   VITE_API_BASE_URL=http://localhost:8000
   VITE_GOOGLE_MAPS_API_KEY=your-google-maps-key # Optional: loads live Google Map when set
   ```
4. Run frontend:
   ```bash
   cd frontend
   npm run dev
   ```

### 2. Running locally with deployed backend
1. Find your deployed Cloud Run URL (e.g., `https://travelwell-backend-xxxxxx.a.run.app`).
2. Update the frontend `.env` file:
   ```env
   VITE_API_BASE_URL=https://travelwell-backend-xxxxxx.a.run.app
   VITE_GOOGLE_MAPS_API_KEY=your-google-maps-key
   ```
3. Run the frontend:
   ```bash
   npm run dev
   ```


Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react/README.md) uses [Babel](https://babeljs.io/) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type aware lint rules:

- Configure the top-level `parserOptions` property like this:

```js
export default tseslint.config({
  languageOptions: {
    // other options...
    parserOptions: {
      project: ['./tsconfig.node.json', './tsconfig.app.json'],
      tsconfigRootDir: import.meta.dirname,
    },
  },
})
```

- Replace `tseslint.configs.recommended` to `tseslint.configs.recommendedTypeChecked` or `tseslint.configs.strictTypeChecked`
- Optionally add `...tseslint.configs.stylisticTypeChecked`
- Install [eslint-plugin-react](https://github.com/jsx-eslint/eslint-plugin-react) and update the config:

```js
// eslint.config.js
import react from 'eslint-plugin-react'

export default tseslint.config({
  // Set the react version
  settings: { react: { version: '18.3' } },
  plugins: {
    // Add the react plugin
    react,
  },
  rules: {
    // other rules...
    // Enable its recommended rules
    ...react.configs.recommended.rules,
    ...react.configs['jsx-runtime'].rules,
  },
})
```
