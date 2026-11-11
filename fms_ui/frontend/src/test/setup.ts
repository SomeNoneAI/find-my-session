// Node 22+ exposes experimental global localStorage/sessionStorage that shadow
// jsdom's implementations inside Vitest. Install plain in-memory Storage objects
// so tests do not depend on the host Node version.
function memoryStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() {
      return values.size;
    },
    clear() {
      values.clear();
    },
    getItem(key) {
      return values.get(key) ?? null;
    },
    key(index) {
      return Array.from(values.keys())[index] ?? null;
    },
    removeItem(key) {
      values.delete(key);
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
  };
}

Object.defineProperty(window, "localStorage", {
  configurable: true,
  value: memoryStorage(),
});

Object.defineProperty(window, "sessionStorage", {
  configurable: true,
  value: memoryStorage(),
});