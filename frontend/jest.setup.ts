// @forgeplan-node: frontend-app-shell
import "@testing-library/jest-dom"

// Mock ResizeObserver — not available in jsdom but used by some UI primitives
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
