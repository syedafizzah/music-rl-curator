import { useState } from "react";
import Login from "./components/Login";
import Player from "./components/Player";
import AdminDashboard from "./components/AdminDashboard";

export default function App() {
  const [user, setUser] = useState(null);

  if (!user) return <Login onLogin={setUser} />;
  if (user.username === "admin") return <AdminDashboard />;
  return <Player user={user} />;
}