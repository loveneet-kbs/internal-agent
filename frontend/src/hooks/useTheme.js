import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "ai-task-agent-theme";

/** Read the theme the inline script in index.html already applied. */
function currentTheme() {
  if (typeof document === "undefined") return "dark";
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

function store(theme) {
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Private mode or blocked site data - the theme still applies for this visit.
  }
}

function hasExplicitChoice() {
  try {
    return Boolean(window.localStorage.getItem(STORAGE_KEY));
  } catch {
    return false;
  }
}

/**
 * Light/dark theme with persistence.
 *
 * The initial class is set by a blocking script in index.html so the page never
 * flashes the wrong theme; this hook only reads and updates it from there.
 */
export default function useTheme() {
  const [theme, setTheme] = useState(currentTheme);

  const apply = useCallback((next) => {
    document.documentElement.classList.toggle("dark", next === "dark");
    setTheme(next);
  }, []);

  const toggle = useCallback(() => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    apply(next);
    store(next);
  }, [apply]);

  // Follow the OS until the user makes an explicit choice.
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: light)");
    const onChange = (event) => {
      if (!hasExplicitChoice()) apply(event.matches ? "light" : "dark");
    };
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [apply]);

  return { theme, toggle, isDark: theme === "dark" };
}
