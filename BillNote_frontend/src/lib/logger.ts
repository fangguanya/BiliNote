// A simple logger utility that only logs in development mode for most levels.
export const logger = {
  log: (...args: any[]) => {
    if (import.meta.env.MODE === 'development') {
      console.log(...args);
    }
  },
  info: (...args: any[]) => {
    if (import.meta.env.MODE === 'development') {
      console.info(...args);
    }
  },
  warn: (...args: any[]) => {
    if (import.meta.env.MODE === 'development') {
      console.warn(...args);
    }
  },
  error: (...args: any[]) => {
    // Errors can be logged in production as well.
    console.error(...args);
  },
}; 