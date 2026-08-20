import { BoardPlaceholder } from "./features/library/BoardPlaceholder";
import { LibraryPage } from "./features/library/LibraryPage";

export function App() {
  if (window.location.pathname.startsWith("/next/p/")) {
    return <BoardPlaceholder />;
  }
  return <LibraryPage />;
}
