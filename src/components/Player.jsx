import { useState, useEffect, useRef } from "react";
import axios from "axios";

const API = "http://127.0.0.1:8000";

export default function Player({ user }) {
    const [songs, setSongs] = useState([]);
    const [currentSong, setCurrentSong] = useState(null);
    const [loading, setLoading] = useState(true);
    const [loadingMore, setLoadingMore] = useState(false);
    const [progress, setProgress] = useState(0);
    const [history, setHistory] = useState([]);
    const [currentTime, setCurrentTime] = useState(0);
    const [searchQuery, setSearchQuery] = useState("");
    const [searchResults, setSearchResults] = useState([]);
    const [searching, setSearching] = useState(false);
    const [activeTab, setActiveTab] = useState("recommended");
    const audioRef = useRef(null);

    const fetchSongs = async (append = false) => {
        append ? setLoadingMore(true) : setLoading(true);
        try {
            const res = await axios.get(`${API}/recommend-many/${user.user_id}`);
            setSongs(prev => append ? [...prev, ...res.data] : res.data);
        } catch {
            console.error("Error fetching songs");
        }
        append ? setLoadingMore(false) : setLoading(false);
    };

    const fetchHistory = async () => {
        try {
            const res = await axios.get(`${API}/history/${user.user_id}`);
            setHistory(res.data);
        } catch {
            console.error("Error fetching history");
        }
    };

    useEffect(() => { fetchSongs(); fetchHistory(); }, []);

    // Track audio progress
    useEffect(() => {
        const audio = audioRef.current;
        if (!audio) return;
        const update = () => {
            setCurrentTime(audio.currentTime);
            setProgress((audio.currentTime / audio.duration) * 100 || 0);
        };
        audio.addEventListener("timeupdate", update);
        return () => audio.removeEventListener("timeupdate", update);
    }, [currentSong]);

    const sendFeedback = async (song, reward) => {
        // Update history instantly in UI — no waiting
        setHistory(prev => [{
            track_name: song.track_name,
            reward,
            played_at: new Date().toISOString()
        }, ...prev].slice(0, 20));

        // Send to backend in background
        axios.post(`${API}/feedback`, {
            user_id: user.user_id,
            track_id: song.track_id,
            track_name: song.track_name,
            reward,
        }).catch(e => console.log(e));
    };

    const handleSelectSong = async (song) => {
        // Play IMMEDIATELY — don't wait for backend
        if (audioRef.current) {
            audioRef.current.pause();
            audioRef.current.src = "";
        }
        setCurrentSong(song);
        setProgress(0);
        setCurrentTime(0);
        setTimeout(() => {
            if (audioRef.current) {
                audioRef.current.load();
                audioRef.current.play().catch(e => console.log(e));
            }
        }, 50);

        // Send feedback in background
        sendFeedback(song, 1.0);
    };

    const handleSkip = () => {
        if (!currentSong) return;
        const reward = currentTime < 10 ? -1.0 : currentTime < 20 ? 0.5 : 2.0;
        sendFeedback(currentSong, reward);
        setCurrentSong(null);
        setProgress(0);
    };

    const handleComplete = () => {
        if (!currentSong) return;
        sendFeedback(currentSong, 2.0);
        setCurrentSong(null);
        setProgress(0);
    };

    const handleFavourite = () => {
        if (!currentSong) return;
        sendFeedback(currentSong, 3.0);
        setCurrentSong(null);
        setProgress(0);
    };

    const handleSearch = async (q) => {
        setSearchQuery(q);
        if (q.length < 2) { setSearchResults([]); return; }
        setSearching(true);
        try {
            const res = await axios.get(`${API}/search/${user.user_id}?q=${encodeURIComponent(q)}`);
            setSearchResults(res.data);
        } catch {
            console.error("Search failed");
        }
        setSearching(false);
    };

    const rewardLabel = (r) => {
        if (r >= 3) return "❤️";
        if (r >= 2) return "✅";
        if (r >= 1) return "▶️";
        if (r >= 0) return "⏭️";
        return "❌";
    };

    const displaySongs = activeTab === "search" ? searchResults : songs;

    return (
        <div style={styles.container}>

            {/* Sidebar */}
            <div style={styles.sidebar}>
                <h2 style={styles.logo}>🎵 Music RL</h2>
                <p style={styles.userBadge}>🤖 {user.username}</p>

                <div style={styles.sidebarSection}>
                    <p style={styles.sidebarLabel}>📜 Recent</p>
                    {history.length === 0
                        ? <p style={styles.emptyText}>No history yet</p>
                        : history.map((h, i) => (
                            <div key={i} style={styles.historyItem}>
                                <span style={styles.historyName}>{h.track_name}</span>
                                <span style={{ fontSize: 14 }}>{rewardLabel(h.reward)}</span>
                            </div>
                        ))}
                </div>
            </div>

            {/* Main Content */}
            <div style={styles.main}>

                {/* Top Bar */}
                <div style={styles.topBar}>
                    <input
                        style={styles.searchInput}
                        placeholder="🔍 Search songs or artists..."
                        value={searchQuery}
                        onChange={e => {
                            handleSearch(e.target.value);
                            setActiveTab(e.target.value ? "search" : "recommended");
                        }}
                    />
                    <button
                        style={styles.refreshBtn}
                        onClick={() => { fetchSongs(false); setActiveTab("recommended"); setSearchQuery(""); }}
                    >
                        🔄
                    </button>
                </div>

                {/* Now Playing */}
                {currentSong && (
                    <div style={styles.nowPlaying}>
                        <img src={currentSong.album_art} alt="" style={styles.npArt} />
                        <div style={styles.npInfo}>
                            <p style={styles.npName}>{currentSong.track_name}</p>
                            <p style={styles.npArtist}>{currentSong.artists}</p>
                            <div style={styles.progressBg}>
                                <div style={{ ...styles.progressFill, width: `${progress}%` }} />
                            </div>
                        </div>
                        <div style={styles.npButtons}>
                            <button style={styles.btnRed} onClick={handleSkip}>⏭️ Skip</button>
                            <button style={styles.btnYellow} onClick={handleFavourite}>❤️</button>
                            <button style={styles.btnGreen} onClick={handleComplete}>✅ Done</button>
                        </div>
                        <audio
                            ref={audioRef}
                            src={currentSong.preview_url}
                            onEnded={handleComplete}
                        />
                    </div>
                )}

                {/* Section Title */}
                <h3 style={styles.sectionTitle}>
                    {activeTab === "recommended" ? "🎯 Made For You" : "🔍 Search Results"}
                </h3>

                {/* Grid */}
                {loading && activeTab === "recommended" ? (
                    <p style={styles.loadingText}>🎵 Agent picking songs...</p>
                ) : (
                    <>
                        {activeTab === "search" && searching && (
                            <p style={styles.loadingText}>Searching...</p>
                        )}
                        {activeTab === "search" && !searching && searchResults.length === 0 && searchQuery.length > 1 && (
                            <p style={styles.loadingText}>No results for "{searchQuery}"</p>
                        )}
                        {activeTab === "search" && searchQuery.length <= 1 && (
                            <p style={styles.loadingText}>Type at least 2 characters...</p>
                        )}

                        <div style={styles.grid}>
                            {displaySongs.map((song, i) => (
                                <div
                                    key={i}
                                    style={{
                                        ...styles.songCard,
                                        ...(currentSong?.track_id === song.track_id
                                            ? styles.songCardActive : {})
                                    }}
                                    onClick={() => handleSelectSong(song)}
                                >
                                    <div style={styles.artWrapper}>
                                        <img src={song.album_art} alt="" style={styles.songArt} />
                                        {currentSong?.track_id === song.track_id && (
                                            <div style={styles.playingOverlay}>▶</div>
                                        )}
                                    </div>
                                    <p style={styles.songName}>{song.track_name}</p>
                                    <p style={styles.songArtist}>{song.artists}</p>
                                    <span style={styles.genreBadge}>{song.genre}</span>
                                </div>
                            ))}
                        </div>

                        {activeTab === "recommended" && (
                            <button
                                style={styles.loadMoreBtn}
                                onClick={() => fetchSongs(true)}
                                disabled={loadingMore}
                            >
                                {loadingMore ? "Loading..." : "⬇️ Load More"}
                            </button>
                        )}
                    </>
                )}
            </div>
        </div>
    );
}

const styles = {
    container: {
        display: "flex",
        minHeight: "100vh",
        background: "#121212",
        color: "#fff",
        fontFamily: "'Segoe UI', sans-serif",
    },

    // Sidebar
    sidebar: {
        width: 240,
        background: "#000",
        padding: "24px 16px",
        display: "flex",
        flexDirection: "column",
        gap: 8,
        overflowY: "auto",
        flexShrink: 0,
        position: "sticky",
        top: 0,
        height: "100vh",
    },
    logo: { margin: "0 0 4px", fontSize: 20, color: "#1db954" },
    userBadge: { margin: "0 0 20px", fontSize: 13, color: "#aaa" },
    sidebarSection: { flex: 1, overflowY: "auto" },
    sidebarLabel: { color: "#fff", fontSize: 14, fontWeight: "bold", margin: "0 0 10px" },
    emptyText: { color: "#555", fontSize: 12 },
    historyItem: {
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "6px 0",
        borderBottom: "1px solid #ffffff0a",
    },
    historyName: {
        color: "#b3b3b3", fontSize: 12,
        overflow: "hidden", textOverflow: "ellipsis",
        whiteSpace: "nowrap", maxWidth: 170,
    },

    // Main
    main: {
        flex: 1,
        padding: "24px 32px",
        overflowY: "auto",
        background: "linear-gradient(180deg, #1a1a2e 0%, #121212 300px)",
    },
    topBar: {
        display: "flex",
        gap: 10,
        marginBottom: 24,
        alignItems: "center",
    },
    searchInput: {
        flex: 1,
        padding: "10px 18px",
        borderRadius: 24,
        border: "none",
        background: "#2a2a2a",
        color: "#fff",
        fontSize: 14,
        outline: "none",
    },
    refreshBtn: {
        padding: "10px 16px",
        borderRadius: 24,
        border: "none",
        background: "#2a2a2a",
        color: "#fff",
        cursor: "pointer",
        fontSize: 16,
    },

    // Now Playing
    nowPlaying: {
        display: "flex",
        alignItems: "center",
        gap: 16,
        padding: "14px 20px",
        background: "#1a1a1a",
        borderRadius: 12,
        marginBottom: 24,
        border: "1px solid #1db95433",
    },
    npArt: { width: 56, height: 56, borderRadius: 8, objectFit: "cover" },
    npInfo: { flex: 1, minWidth: 0 },
    npName: {
        margin: 0, fontSize: 15, fontWeight: "bold",
        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
    },
    npArtist: { margin: "2px 0 8px", fontSize: 12, color: "#aaa" },
    progressBg: { height: 4, background: "#ffffff22", borderRadius: 2 },
    progressFill: {
        height: "100%", background: "#1db954",
        borderRadius: 2, transition: "width 0.3s",
    },
    npButtons: { display: "flex", gap: 8, flexShrink: 0 },
    btnRed: {
        padding: "8px 14px", borderRadius: 20, border: "none",
        background: "#ff6b6b22", color: "#ff6b6b",
        cursor: "pointer", fontWeight: "bold", fontSize: 13,
    },
    btnYellow: {
        padding: "8px 14px", borderRadius: 20, border: "none",
        background: "#ffd70022", color: "#ffd700",
        cursor: "pointer", fontWeight: "bold", fontSize: 13,
    },
    btnGreen: {
        padding: "8px 14px", borderRadius: 20, border: "none",
        background: "#1db95422", color: "#1db954",
        cursor: "pointer", fontWeight: "bold", fontSize: 13,
    },

    // Section
    sectionTitle: { margin: "0 0 20px", fontSize: 22, fontWeight: "bold" },
    loadingText: { color: "#aaa", padding: 40, textAlign: "center" },

    // Grid
    grid: {
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(170px, 1fr))",
        gap: 20,
        marginBottom: 24,
    },
    songCard: {
        background: "#181818",
        borderRadius: 8,
        padding: 16,
        cursor: "pointer",
        transition: "background 0.15s",
    },
    songCardActive: {
        background: "#282828",
        outline: "1px solid #1db954",
    },
    artWrapper: { position: "relative", marginBottom: 12 },
    songArt: {
        width: "100%", aspectRatio: "1",
        borderRadius: 6, objectFit: "cover",
        boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
        display: "block",
    },
    playingOverlay: {
        position: "absolute", bottom: 8, right: 8,
        background: "#1db954", color: "#000",
        width: 32, height: 32, borderRadius: "50%",
        display: "flex", alignItems: "center",
        justifyContent: "center", fontSize: 14, fontWeight: "bold",
    },
    songName: {
        margin: "0 0 4px", fontSize: 14, fontWeight: "bold",
        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
    },
    songArtist: {
        margin: "0 0 8px", fontSize: 12, color: "#b3b3b3",
        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
    },
    genreBadge: {
        background: "#ffffff11", color: "#1db954",
        padding: "2px 8px", borderRadius: 20, fontSize: 10,
    },
    loadMoreBtn: {
        width: "100%", padding: 14, borderRadius: 8, border: "none",
        background: "#282828", color: "#fff",
        cursor: "pointer", fontSize: 14, marginBottom: 40,
    },
};