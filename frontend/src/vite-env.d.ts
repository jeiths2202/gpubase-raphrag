/// <reference types="vite/client" />

// Node.js global types for test files
declare const global: typeof globalThis;
declare const process: {
  env: {
    NODE_ENV: string;
    VISUAL_REGRESSION?: string;
    [key: string]: string | undefined;
  };
};

// Vite environment variables
interface ImportMetaEnv {
  // Application
  readonly VITE_APP_ENV: string;

  // API
  readonly VITE_API_URL: string;
  readonly VITE_API_BASE_URL: string; // Legacy alias

  // Authentication
  readonly VITE_GOOGLE_CLIENT_ID: string;
  readonly VITE_SSO_PROVIDER_URL: string;

  // Service Endpoints
  readonly VITE_NEO4J_BROWSER_URL: string;
  readonly VITE_NEMOTRON_LLM_URL: string;
  readonly VITE_NEMO_EMBEDDING_URL: string;
  readonly VITE_MISTRAL_CODER_URL: string;

  // Feature Flags
  readonly VITE_ENABLE_MINDMAP: string;
  readonly VITE_ENABLE_KNOWLEDGE_GRAPH: string;
  readonly VITE_ENABLE_VISION: string;

  // UI Configuration
  readonly VITE_DEFAULT_THEME: string;
  readonly VITE_DEFAULT_LANGUAGE: string;

  // Vite built-in
  readonly MODE: string;
  readonly DEV: boolean;
  readonly PROD: boolean;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
