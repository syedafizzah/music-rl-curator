import { useState } from "react";
import axios from "axios";

const API = "http://127.0.0.1:8000";

export default function Login({ onLogin }) {
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [isRegister, setIsRegister] = useState(false);
    const [error, setError] = useState("");

    const handleSubmit = async () => {
        try {
            const endpoint = isRegister ? "/register" : "/login";
            const res = await axios.post(`${API}${endpoint}`, { username, password });
            onLogin(res.data);
        } catch (e) {
            setError(e.response?.data?.detail || "Something went wrong");
        }
    };

    return (
        <div style={styles.container}>
            <div style={styles.box}>
                <h1 style={styles.title}>🎵 Music RL Player</h1>
                <p style={styles.subtitle}>Powered by Reinforcement Learning</p>

                <input
                    style={styles.input}
                    placeholder="Username"
                    value={username}
                    onChange={e => setUsername(e.target.value)}
                />
                <input
                    style={styles.input}
                    placeholder="Password"
                    type="password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                />

                {error && <p style={styles.error}>{error}</p>}

                <button style={styles.btn} onClick={handleSubmit}>
                    {isRegister ? "Register" : "Login"}
                </button>

                <p style={styles.toggle}>
                    {isRegister ? "Already have account? " : "No account? "}
                    <span
                        style={styles.link}
                        onClick={() => { setIsRegister(!isRegister); setError(""); }}
                    >
                        {isRegister ? "Login" : "Register"}
                    </span>
                </p>
            </div>
        </div>
    );
}

const styles = {
    container: {
        minHeight: "100vh",
        background: "linear-gradient(135deg, #1a1a2e, #16213e, #0f3460)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
    },
    box: {
        background: "rgba(255,255,255,0.05)",
        borderRadius: 20,
        padding: 40,
        width: 340,
        display: "flex",
        flexDirection: "column",
        gap: 12,
        backdropFilter: "blur(10px)",
        border: "1px solid rgba(255,255,255,0.1)",
    },
    title: { color: "#fff", textAlign: "center", margin: 0, fontSize: 24 },
    subtitle: { color: "#aaa", textAlign: "center", margin: 0, fontSize: 13 },
    input: {
        padding: "12px 16px",
        borderRadius: 10,
        border: "1px solid rgba(255,255,255,0.2)",
        background: "rgba(255,255,255,0.08)",
        color: "#fff",
        fontSize: 15,
        outline: "none",
    },
    btn: {
        padding: "13px",
        borderRadius: 10,
        border: "none",
        background: "#1db954",
        color: "#fff",
        fontSize: 16,
        fontWeight: "bold",
        cursor: "pointer",
        marginTop: 4,
    },
    error: { color: "#ff6b6b", textAlign: "center", margin: 0, fontSize: 13 },
    toggle: { color: "#aaa", textAlign: "center", margin: 0, fontSize: 13 },
    link: { color: "#1db954", cursor: "pointer", fontWeight: "bold" },
};