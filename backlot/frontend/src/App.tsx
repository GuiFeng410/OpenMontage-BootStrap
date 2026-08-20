import { BoardPage } from "./features/board/BoardPage";
import { LibraryPage } from "./features/library/LibraryPage";

export function App() {
  if (window.location.pathname.startsWith("/next/p/")) {
    return <BoardPage />;
  }
  return <LibraryPage />;
}
