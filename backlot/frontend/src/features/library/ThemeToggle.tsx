import { useEffect, useState } from "react";

export function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark">(() =>
    localStorage.getItem("backlot.theme") === "light" ? "light" : "dark",
  );
  const next = theme === "light" ? "dark" : "light";
  const nextLabel = next === "light" ? "浅色" : "深色";

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("backlot.theme", theme);
  }, [theme]);

  return (
    <button
      className="theme-toggle"
      type="button"
      title={`切换到${nextLabel}主题`}
      aria-label={`切换到${nextLabel}主题`}
      aria-pressed={theme === "light"}
      onClick={() => setTheme(next)}
    >
      <span className="theme-toggle-icon" aria-hidden="true">
        {theme === "light" ? "☾" : "☀"}
      </span>
    </button>
  );
}
