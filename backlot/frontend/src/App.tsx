import { BoardPage } from "./features/board/BoardPage";
import { LibraryPage } from "./features/library/LibraryPage";

export function App() {
  const path = window.location.pathname;
  if (path.startsWith("/next/p/") || path.startsWith("/p/")) {
    return <BoardPage />;
  }
  return <LibraryPage />;
}
