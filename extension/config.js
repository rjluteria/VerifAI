import { backend } from "./core.js";

// Developer configuration is packaged code, never a stored user preference.
export const SERVICE_ORIGIN = backend("https://verifai-ekan.onrender.com");

// Developer-only native acceptance clock; disabled in normal packages.
export const BENCHMARK_TIMING = false;
