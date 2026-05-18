import { useState, useEffect } from "react";
import axios from "axios";

const API = "http://127.0.0.1:8000";

export default function AdminDashboard() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [selected, setSelected] = useState(null);

    const fetch = async () => {
        setLoading(true);
        const res = await axios.get(`${API}/admin/stats`);
        setData(res.data);
        if (res.data.users.length > 0) setSelected(res.data.users[0]);
        setLoading(false);
    };

    useEffect(() => { fetch(); }, []);

    const rewardColor = (r) => {
        if (r >= 3) return "#ffd700";
        if (r >= 2) return "#1db954";
        if (r >= 1) return "#4a9eff";
        if (r >= 0) return "#ff9500";
        return "#ff6b6b";
    };

    if (loading) return (
        <div style={styles.center}>
            <p style={{ color: "#aaa" }}>Loading admin data...</p>
        </div>
    );

    return (
        <div style={styles.container}>

            {/* Header */}
            <div style={styles.header}>
                <h1 style={styles.title}>🤖 RL Admin Dashboard</h1>
                <button style={styles.refreshBtn} onClick={fetch}>🔄 Refresh</button>
            </div>

            {/* Top Stats */}
            <div style={styles.topCards}>
                <div style={styles.statCard}>
                    <p style={styles.statNum}>{data.total_users}</p>
                    <p style={styles.statLabel}>Total Users</p>
                </div>
                <div style={styles.statCard}>
                    <p style={styles.statNum}>{data.total_songs_played}</p>
                    <p style={styles.statLabel}>Songs Played</p>
                </div>
                <div style={styles.statCard}>
                    <p style={styles.statNum}>
                        {data.users.length > 0
                            ? (data.users.reduce((a, b) => a + b.avg_reward, 0) / data.users.length).toFixed(2)
                            : "N/A"}
                    </p>
                    <p style={styles.statLabel}>Avg Reward</p>
                </div>
                <div style={styles.statCard}>
                    <p style={styles.statNum}>LinUCB</p>
                    <p style={styles.statLabel}>Algorithm</p>
                </div>
            </div>

            {data.users.length === 0 ? (
                <p style={{ color: "#aaa", textAlign: "center", padding: 40 }}>
                    No users have played songs yet
                </p>
            ) : (
                <div style={styles.mainRow}>

                    {/* User List */}
                    <div style={styles.userList}>
                        <p style={styles.sectionLabel}>👥 Users</p>
                        {data.users.map((u, i) => (
                            <div
                                key={i}
                                style={{
                                    ...styles.userCard,
                                    ...(selected?.user_id === u.user_id ? styles.userCardActive : {})
                                }}
                                onClick={() => setSelected(u)}
                            >
                                <p style={styles.userName}>{u.username}</p>
                                <p style={styles.userMeta}>{u.total_songs} songs</p>
                                <p style={{ ...styles.userMeta, color: rewardColor(u.avg_reward) }}>
                                    avg: {u.avg_reward}
                                </p>
                            </div>
                        ))}
                    </div>

                    {/* User Detail */}
                    {selected && (
                        <div style={styles.detail}>
                            <h2 style={styles.detailTitle}>📊 {selected.username}</h2>

                            {/* Reward Breakdown */}
                            <div style={styles.section}>
                                <p style={styles.sectionLabel}>🎯 Reward Breakdown</p>
                                <div style={styles.breakdownRow}>
                                    {[
                                        { label: "Completed", val: selected.reward_breakdown.completed, color: "#1db954" },
                                        { label: "Favourited", val: selected.reward_breakdown.favourited, color: "#ffd700" },
                                        { label: "Chosen", val: selected.reward_breakdown.chosen, color: "#4a9eff" },
                                        { label: "Skipped", val: selected.reward_breakdown.skipped, color: "#ff6b6b" },
                                    ].map((item, i) => (
                                        <div key={i} style={styles.breakdownCard}>
                                            <p style={{ ...styles.breakdownNum, color: item.color }}>{item.val}</p>
                                            <p style={styles.breakdownLabel}>{item.label}</p>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            {/* Learning Curve */}
                            <div style={styles.section}>
                                <p style={styles.sectionLabel}>📈 Learning Curve (Rolling Avg Reward)</p>
                                <div style={styles.chartWrapper}>
                                    {selected.rewards_over_time.map((r, i) => (
                                        <div
                                            key={i}
                                            title={`Song ${i + 1}: ${r}`}
                                            style={{
                                                ...styles.bar,
                                                height: `${Math.max(4, ((r + 1) / 4) * 100)}%`,
                                                background: r > 1.5 ? "#1db954" : r > 0 ? "#ff9500" : "#ff6b6b",
                                            }}
                                        />
                                    ))}
                                </div>
                                <div style={styles.chartLabels}>
                                    <span>Song 1</span>
                                    <span>Song {selected.rewards_over_time.length}</span>
                                </div>
                                <p style={styles.chartHint}>
                                    Green = good | Orange = neutral | Red = skipped
                                </p>
                            </div>

                            {/* Agent Preferences */}
                            <div style={styles.section}>
                                <p style={styles.sectionLabel}>🧠 What Agent Learned (Feature Weights)</p>
                                {Object.entries(selected.learned_preferences).map(([feat, val], i) => {
                                    const pct = Math.min(100, Math.abs(val) * 200);
                                    return (
                                        <div key={i} style={styles.prefRow}>
                                            <span style={styles.prefLabel}>{feat}</span>
                                            <div style={styles.prefBarBg}>
                                                <div style={{
                                                    ...styles.prefBarFill,
                                                    width: `${pct}%`,
                                                    background: val > 0 ? "#1db954" : "#ff6b6b",
                                                }} />
                                            </div>
                                            <span style={{
                                                ...styles.prefVal,
                                                color: val > 0 ? "#1db954" : "#ff6b6b"
                                            }}>
                                                {val > 0 ? "+" : ""}{val}
                                            </span>
                                        </div>
                                    );
                                })}
                                <p style={styles.chartHint}>
                                    Green = user likes this feature | Red = user dislikes
                                </p>
                            </div>

                            {/* Recent Songs */}
                            <div style={styles.section}>
                                <p style={styles.sectionLabel}>🎵 Last 5 Songs</p>
                                {selected.recent_songs.map((s, i) => (
                                    <div key={i} style={styles.recentRow}>
                                        <span style={styles.recentName}>{s.name}</span>
                                        <span style={{ color: rewardColor(s.reward), fontSize: 13 }}>
                                            reward: {s.reward}
                                        </span>
                                    </div>
                                ))}
                            </div>

                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

const styles = {
    container: {
        minHeight: "100vh",
        background: "#121212",
        color: "#fff",
        fontFamily: "'Segoe UI', sans-serif",
        padding: "24px 32px",
    },
    center: {
        minHeight: "100vh", display: "flex",
        alignItems: "center", justifyContent: "center",
        background: "#121212",
    },
    header: {
        display: "flex", justifyContent: "space-between",
        alignItems: "center", marginBottom: 24,
    },
    title: { margin: 0, fontSize: 24, color: "#1db954" },
    refreshBtn: {
        padding: "8px 18px", borderRadius: 20, border: "none",
        background: "#282828", color: "#fff",
        cursor: "pointer", fontSize: 13,
    },

    // Top Cards
    topCards: {
        display: "grid",
        gridTemplateColumns: "repeat(4, 1fr)",
        gap: 16, marginBottom: 28,
    },
    statCard: {
        background: "#181818", borderRadius: 12,
        padding: "20px 16px", textAlign: "center",
        border: "1px solid #282828",
    },
    statNum: { margin: "0 0 6px", fontSize: 28, fontWeight: "bold", color: "#1db954" },
    statLabel: { margin: 0, fontSize: 12, color: "#aaa" },

    // Main Row
    mainRow: {
        display: "flex", gap: 20, alignItems: "flex-start",
    },

    // User List
    userList: {
        width: 200, flexShrink: 0,
    },
    userCard: {
        background: "#181818", borderRadius: 10,
        padding: "12px 14px", marginBottom: 8,
        cursor: "pointer", border: "1px solid #282828",
    },
    userCardActive: {
        border: "1px solid #1db954",
        background: "#1db95411",
    },
    userName: { margin: "0 0 4px", fontSize: 14, fontWeight: "bold" },
    userMeta: { margin: 0, fontSize: 12, color: "#aaa" },

    // Detail
    detail: { flex: 1 },
    detailTitle: { margin: "0 0 20px", fontSize: 20 },
    section: { marginBottom: 28 },
    sectionLabel: {
        color: "#fff", fontSize: 14,
        fontWeight: "bold", margin: "0 0 12px",
    },

    // Breakdown
    breakdownRow: { display: "flex", gap: 12 },
    breakdownCard: {
        flex: 1, background: "#181818",
        borderRadius: 10, padding: 16,
        textAlign: "center", border: "1px solid #282828",
    },
    breakdownNum: { margin: "0 0 4px", fontSize: 24, fontWeight: "bold" },
    breakdownLabel: { margin: 0, fontSize: 11, color: "#aaa" },

    // Chart
    chartWrapper: {
        display: "flex", alignItems: "flex-end",
        height: 120, gap: 2,
        background: "#181818", borderRadius: 8,
        padding: "10px 10px 0", marginBottom: 4,
        overflow: "hidden",
    },
    bar: {
        flex: 1, borderRadius: "3px 3px 0 0",
        minWidth: 4, transition: "height 0.3s",
    },
    chartLabels: {
        display: "flex", justifyContent: "space-between",
        fontSize: 11, color: "#555", margin: "4px 0",
    },
    chartHint: { color: "#555", fontSize: 11, margin: "4px 0 0" },

    // Preferences
    prefRow: {
        display: "flex", alignItems: "center",
        gap: 10, marginBottom: 8,
    },
    prefLabel: { width: 120, fontSize: 12, color: "#aaa", flexShrink: 0 },
    prefBarBg: { flex: 1, height: 8, background: "#282828", borderRadius: 4 },
    prefBarFill: { height: "100%", borderRadius: 4, transition: "width 0.5s" },
    prefVal: { width: 50, fontSize: 11, textAlign: "right", flexShrink: 0 },

    // Recent
    recentRow: {
        display: "flex", justifyContent: "space-between",
        padding: "8px 0", borderBottom: "1px solid #282828",
    },
    recentName: {
        fontSize: 13, color: "#b3b3b3",
        overflow: "hidden", textOverflow: "ellipsis",
        whiteSpace: "nowrap", maxWidth: 400,
    },
};