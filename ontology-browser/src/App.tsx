import { Navigate, Route, Routes } from "react-router-dom";
import GraphPage from "@/pages/GraphPage";

function HomePage() {
  return <Navigate to="/graph/active" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/graph" element={<Navigate to="/graph/active" replace />} />
      <Route path="/graph/:packId" element={<GraphPage />} />
      <Route path="*" element={<Navigate to="/graph/active" replace />} />
    </Routes>
  );
}
