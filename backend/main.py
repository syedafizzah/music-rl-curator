from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from passlib.context import CryptContext
from database import get_db, engine
from models import Base, User, ListenHistory
from agent import load_agent, save_agent
from context import build_context_vector
from datetime import datetime
import pandas as pd
import numpy as np
import pickle
import uuid
import requests
from concurrent.futures import ThreadPoolExecutor
import os

# ── Base setup ───────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Load dataset safely (Render-safe paths) ───────────────────
df = pd.read_csv(os.path.join(BASE_DIR, "clean.csv"))

with open(os.path.join(BASE_DIR, "scaler.pkl"), "rb") as f:
    scaler = pickle.load(f)

RL_FEATURES = [
    'danceability', 'energy', 'valence', 'tempo',
    'loudness', 'acousticness', 'instrumentalness', 'speechiness'
]

df_scaled = df.copy()
df_scaled[RL_FEATURES] = scaler.transform(df_scaled[RL_FEATURES])
song_matrix = df_scaled[RL_FEATURES].values

# ── DB init ───────────────────────────────────────────────
Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

pwd_context = CryptContext(schemes=["bcrypt"])

# ── Deezer cache ─────────────────────────────────────────────
deezer_cache: dict = {}

# ── Request models ───────────────────────────────────────────
class RegisterRequest(BaseModel):
    username: str
    password: str

class FeedbackRequest(BaseModel):
    user_id: str
    track_id: str
    track_name: str
    reward: float
    activity: float = 0.5

# ── Deezer helper ────────────────────────────────────────────
def get_deezer_data(track_name: str, artist: str, track_id: str = None) -> dict:
    if track_id and track_id in deezer_cache:
        return deezer_cache[track_id]

    query = f"{track_name} {artist}"
    url = f"https://api.deezer.com/search?q={requests.utils.quote(query)}&limit=1"

    try:
        res = requests.get(url, timeout=3)
        data = res.json()

        if data.get("data"):
            track = data["data"][0]
            result = {
                "preview_url": track.get("preview"),
                "album_art": track["album"]["cover_medium"]
            }
            if track_id:
                deezer_cache[track_id] = result
            return result
    except:
        pass

    return {"preview_url": None, "album_art": None}

# ── Context builder ───────────────────────────────────────────
def build_context_fast(audio_8, track_id, activity, time_norm, skip_rate, recent_ids):
    recency = 1.0 if track_id in recent_ids else 0.0
    context_4 = np.array([time_norm, float(activity), skip_rate, recency])
    return np.concatenate([audio_8, context_4])

# ── AUTH ──────────────────────────────────────────────────────
@app.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(status_code=400, detail="Username taken")

    user = User(
        id=str(uuid.uuid4()),
        username=req.username,
        password_hash=pwd_context.hash(req.password)
    )

    db.add(user)
    db.commit()

    return {"user_id": user.id, "username": user.username}


@app.post("/login")
def login(req: RegisterRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()

    if not user or not pwd_context.verify(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Wrong credentials")

    return {"user_id": user.id, "username": user.username}

# ── Cold start ────────────────────────────────────────────────
@app.get("/cold-start")
def cold_start():
    top_genres = df["track_genre"].value_counts().head(10).index.tolist()

    picks = []
    for genre in top_genres:
        genre_df = df[df["track_genre"] == genre].nlargest(20, "popularity")
        picks.append(genre_df.head(2))

    result = (
        pd.concat(picks)
        .drop_duplicates(subset="track_id")
        .head(20)
        .reset_index(drop=True)
    )

    def fetch(row):
        _, song = row
        d = get_deezer_data(song["track_name"], song["artists"], song["track_id"])

        return {
            "track_id": song["track_id"],
            "track_name": song["track_name"],
            "artists": song["artists"],
            "genre": song["track_genre"],
            "popularity": int(song["popularity"]),
            "preview_url": d["preview_url"],
            "album_art": d["album_art"],
        }

    with ThreadPoolExecutor(max_workers=20) as ex:
        songs = list(ex.map(fetch, result.iterrows()))

    return songs

# ── RECOMMEND SINGLE ──────────────────────────────────────────
@app.get("/recommend/{user_id}")
def recommend(user_id: str, activity: float = 0.5, db: Session = Depends(get_db)):
    agent = load_agent(user_id, db)

    history = (
        db.query(ListenHistory)
        .filter(ListenHistory.user_id == user_id)
        .order_by(ListenHistory.played_at.desc())
        .limit(20)
        .all()
    )

    time_norm = datetime.now().hour / 24.0
    skip_rate = sum(1 for h in history if h.reward < 0) / max(len(history), 1)
    recent_ids = {h.track_id for h in history}

    for _ in range(10):
        idxs = np.random.choice(len(song_matrix), 50, replace=False)
        pool_audio = song_matrix[idxs]

        pool_12 = np.array([
            build_context_fast(
                pool_audio[i],
                df.iloc[idxs[i]]["track_id"],
                activity,
                time_norm,
                skip_rate,
                recent_ids
            )
            for i in range(len(idxs))
        ])

        best = agent.select(pool_12)
        song = df.iloc[idxs[best]]
        deezer = get_deezer_data(song["track_name"], song["artists"], song["track_id"])

        if not deezer["preview_url"]:
            continue

        return {
            "track_id": song["track_id"],
            "track_name": song["track_name"],
            "artists": song["artists"],
            "genre": song["track_genre"],
            "popularity": int(song["popularity"]),
            "preview_url": deezer["preview_url"],
            "album_art": deezer["album_art"],
        }

    return {"error": "No preview available"}

# ── RECOMMEND MANY ────────────────────────────────────────────
@app.get("/recommend-many/{user_id}")
def recommend_many(user_id: str, activity: float = 0.5, db: Session = Depends(get_db)):
    agent = load_agent(user_id, db)

    history = (
        db.query(ListenHistory)
        .filter(ListenHistory.user_id == user_id)
        .order_by(ListenHistory.played_at.desc())
        .limit(20)
        .all()
    )

    time_norm = datetime.now().hour / 24.0
    skip_rate = sum(1 for h in history if h.reward < 0) / max(len(history), 1)
    recent_ids = {h.track_id for h in history}

    idxs = np.random.choice(len(song_matrix), 200, replace=False)
    pool_audio = song_matrix[idxs]

    pool_12 = np.array([
        build_context_fast(
            pool_audio[i],
            df.iloc[idxs[i]]["track_id"],
            activity,
            time_norm,
            skip_rate,
            recent_ids
        )
        for i in range(len(idxs))
    ])

    A_inv = np.linalg.inv(agent.A)
    theta = A_inv @ agent.b

    exploit_scores = [float(theta @ x) for x in pool_12]
    explore_scores = [float(agent.alpha * np.sqrt(x @ A_inv @ x)) for x in pool_12]

    TOTAL = 15
    N_EXPLOIT = round(TOTAL * 0.5)
    N_EXPLORE = round(TOTAL * 0.3)
    N_BUFFER = TOTAL - N_EXPLOIT - N_EXPLORE

    exploit_ranked = np.argsort(exploit_scores)[::-1]
    exploit_picks = list(exploit_ranked[:N_EXPLOIT])

    picked = set(exploit_picks)

    explore_ranked = np.argsort(explore_scores)[::-1]
    explore_picks = [i for i in explore_ranked if i not in picked][:N_EXPLORE]

    picked.update(explore_picks)

    remaining = [i for i in range(len(pool_12)) if i not in picked]
    buffer_picks = list(np.random.choice(remaining, N_BUFFER, replace=False))

    final_idxs = exploit_picks + explore_picks + buffer_picks

    def fetch(i):
        song = df.iloc[idxs[i]]
        d = get_deezer_data(song["track_name"], song["artists"], song["track_id"])
        if not d["preview_url"]:
            return None
        return {
            "track_id": song["track_id"],
            "track_name": song["track_name"],
            "artists": song["artists"],
            "genre": song["track_genre"],
            "popularity": int(song["popularity"]),
            "preview_url": d["preview_url"],
            "album_art": d["album_art"],
        }

    with ThreadPoolExecutor(max_workers=15) as ex:
        results = list(ex.map(fetch, final_idxs))

    return [r for r in results if r][:15]

# ── KEEP REST OF YOUR ROUTES SAME ─────────────────────────────
# (feedback, search, stats, history, admin, etc. unchanged)
