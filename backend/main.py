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

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Load data once at startup ──────────────────────────────────────────────
RL_FEATURES = ['danceability','energy','valence','tempo',
               'loudness','acousticness','instrumentalness','speechiness']

df = pd.read_csv('clean.csv')
with open('scaler.pkl', 'rb') as f:
    scaler = pickle.load(f)

df_scaled              = df.copy()
df_scaled[RL_FEATURES] = scaler.transform(df[RL_FEATURES])
song_matrix            = df_scaled[RL_FEATURES].values   # (N, 8)

pwd_context = CryptContext(schemes=["bcrypt"])

# ── In-memory Deezer cache (survives for lifetime of process) ──────────────
# Key: track_id → {preview_url, album_art}
# This is the biggest speed win — same song never fetched twice from Deezer
deezer_cache: dict = {}


# ── Request models ─────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    username: str
    password: str

class FeedbackRequest(BaseModel):
    user_id:    str
    track_id:   str
    track_name: str
    reward:     float
    activity:   float = 0.5   # 0.0=relaxing, 0.5=working, 1.0=exercising


# ── Deezer helper with caching ─────────────────────────────────────────────
def get_deezer_data(track_name: str, artist: str, track_id: str = None) -> dict:
    # Return cached result instantly — no HTTP call
    if track_id and track_id in deezer_cache:
        return deezer_cache[track_id]

    query = f"{track_name} {artist}"
    url   = f"https://api.deezer.com/search?q={requests.utils.quote(query)}&limit=1"
    try:
        res  = requests.get(url, timeout=3)   # reduced from 5 → 3
        data = res.json()
        if data.get('data'):
            track  = data['data'][0]
            result = {
                "preview_url": track.get('preview'),
                "album_art":   track['album']['cover_medium']
            }
            if track_id:
                deezer_cache[track_id] = result   # cache for next time
            return result
    except Exception:
        pass
    return {"preview_url": None, "album_art": None}


# ── Context builder (no DB — caller passes history in) ────────────────────
def build_context_fast(
    audio_8:    np.ndarray,
    track_id:   str,
    activity:   float,
    time_norm:  float,
    skip_rate:  float,
    recent_ids: set
) -> np.ndarray:
    """
    Builds 12-dim vector from pre-fetched session data.
    Called once per candidate — no DB round-trip inside.
    """
    recency   = 1.0 if track_id in recent_ids else 0.0
    context_4 = np.array([time_norm, float(activity), skip_rate, recency])
    return np.concatenate([audio_8, context_4])


# ── Auth ───────────────────────────────────────────────────────────────────
@app.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(status_code=400, detail="Username taken")
    user = User(
        id            = str(uuid.uuid4()),
        username      = req.username,
        password_hash = pwd_context.hash(req.password)
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


# ── Cold start (parallel Deezer calls) ────────────────────────────────────
@app.get("/cold-start")
def cold_start():
    top_genres = df['track_genre'].value_counts().head(10).index.tolist()
    picks = []
    for genre in top_genres:
        genre_df = df[df['track_genre'] == genre].nlargest(20, 'popularity')
        picks.append(genre_df.head(2))
    result = (pd.concat(picks)
                .drop_duplicates(subset='track_id')
                .head(20)
                .reset_index(drop=True))

    def fetch(row):
        _, song = row
        d = get_deezer_data(song['track_name'], song['artists'], song['track_id'])
        return {
            "track_id":    song['track_id'],
            "track_name":  song['track_name'],
            "artists":     song['artists'],
            "genre":       song['track_genre'],
            "popularity":  int(song['popularity']),
            "preview_url": d['preview_url'],
            "album_art":   d['album_art'],
        }

    # All 20 Deezer calls in parallel — was sequential before
    with ThreadPoolExecutor(max_workers=20) as ex:
        songs = list(ex.map(fetch, result.iterrows()))
    return songs


# ── Recommend single song ──────────────────────────────────────────────────
@app.get("/recommend/{user_id}")
def recommend(user_id: str, activity: float = 0.5, db: Session = Depends(get_db)):
    agent = load_agent(user_id, db)

    # Fetch history once
    history    = db.query(ListenHistory)\
                   .filter(ListenHistory.user_id == user_id)\
                   .order_by(ListenHistory.played_at.desc())\
                   .limit(20).all()
    time_norm  = datetime.now().hour / 24.0
    skip_rate  = sum(1 for h in history if h.reward < 0) / max(len(history), 1)
    recent_ids = {h.track_id for h in history}

    for _ in range(10):
        idxs       = np.random.choice(len(song_matrix), 50, replace=False)
        pool_audio = song_matrix[idxs]
        pool_12    = np.array([
            build_context_fast(pool_audio[i], df.iloc[idxs[i]]['track_id'],
                               activity, time_norm, skip_rate, recent_ids)
            for i in range(len(idxs))
        ])

        best   = agent.select(pool_12)
        song   = df.iloc[idxs[best]]
        deezer = get_deezer_data(song['track_name'], song['artists'], song['track_id'])

        if not deezer['preview_url']:
            continue

        return {
            "track_id":    song['track_id'],
            "track_name":  song['track_name'],
            "artists":     song['artists'],
            "genre":       song['track_genre'],
            "popularity":  int(song['popularity']),
            "preview_url": deezer['preview_url'],
            "album_art":   deezer['album_art'],
        }

    return {"error": "No preview available, try again"}


# ── Recommend many (Spotify-style queue) ───────────────────────────────────
@app.get("/recommend-many/{user_id}")
def recommend_many(user_id: str, activity: float = 0.5, db: Session = Depends(get_db)):
    agent = load_agent(user_id, db)

    # FIX: fetch history ONCE — was fetching once per candidate (200 DB hits)
    history    = db.query(ListenHistory)\
                   .filter(ListenHistory.user_id == user_id)\
                   .order_by(ListenHistory.played_at.desc())\
                   .limit(20).all()
    time_norm  = datetime.now().hour / 24.0
    skip_rate  = sum(1 for h in history if h.reward < 0) / max(len(history), 1)
    recent_ids = {h.track_id for h in history}

    # Sample candidate pool
    idxs       = np.random.choice(len(song_matrix), 200, replace=False)
    pool_audio = song_matrix[idxs]

    # Build all 200 context vectors — no DB calls inside
    pool_12 = np.array([
        build_context_fast(pool_audio[i], df.iloc[idxs[i]]['track_id'],
                           activity, time_norm, skip_rate, recent_ids)
        for i in range(len(idxs))
    ])

    # FIX: compute A_inv once — not repeatedly inside select()
    A_inv  = np.linalg.inv(agent.A)
    theta  = A_inv @ agent.b

    exploit_scores = [float(theta @ x)                             for x in pool_12]
    explore_scores = [float(agent.alpha * np.sqrt(x @ A_inv @ x)) for x in pool_12]

    TOTAL     = 15
    N_EXPLOIT = round(TOTAL * 0.50)   # 7-8 known-good songs
    N_EXPLORE = round(TOTAL * 0.30)   # 4-5 uncertain songs
    N_BUFFER  = TOTAL - N_EXPLOIT - N_EXPLORE  # 3 random

    exploit_ranked = np.argsort(exploit_scores)[::-1]
    exploit_picks  = list(exploit_ranked[:N_EXPLOIT])

    picked = set(exploit_picks)
    explore_ranked = np.argsort(explore_scores)[::-1]
    explore_picks  = [i for i in explore_ranked if i not in picked][:N_EXPLORE]

    picked.update(explore_picks)
    remaining    = [i for i in range(len(pool_12)) if i not in picked]
    buffer_picks = list(np.random.choice(remaining, min(N_BUFFER, len(remaining)), replace=False))

    final_idxs = exploit_picks + explore_picks + buffer_picks

    def fetch(i):
        song = df.iloc[idxs[i]]
        d    = get_deezer_data(song['track_name'], song['artists'], song['track_id'])
        if not d['preview_url']:
            return None
        return {
            "track_id":    song['track_id'],
            "track_name":  song['track_name'],
            "artists":     song['artists'],
            "genre":       song['track_genre'],
            "popularity":  int(song['popularity']),
            "preview_url": d['preview_url'],
            "album_art":   d['album_art'],
        }

    # Parallel Deezer fetch for all 15 candidates
    with ThreadPoolExecutor(max_workers=15) as ex:
        results = list(ex.map(fetch, final_idxs))

    return [r for r in results if r][:15]


# ── Search ─────────────────────────────────────────────────────────────────
@app.get("/search/{user_id}")
def search(user_id: str, q: str, db: Session = Depends(get_db)):
    if not q:
        return []
    mask    = (
        df['track_name'].str.contains(q, case=False, na=False) |
        df['artists'].str.contains(q, case=False, na=False)
    )
    results = df[mask].head(20)
    songs   = []

    def fetch(row):
        _, song = row
        d = get_deezer_data(song['track_name'], song['artists'], song['track_id'])
        if not d['preview_url']:
            return None
        return {
            "track_id":    song['track_id'],
            "track_name":  song['track_name'],
            "artists":     song['artists'],
            "genre":       song['track_genre'],
            "popularity":  int(song['popularity']),
            "preview_url": d['preview_url'],
            "album_art":   d['album_art'],
        }

    with ThreadPoolExecutor(max_workers=10) as ex:
        raw = list(ex.map(fetch, results.iterrows()))

    return [r for r in raw if r][:10]


# ── Feedback — agent learns here ───────────────────────────────────────────
@app.post("/feedback")
def feedback(req: FeedbackRequest, db: Session = Depends(get_db)):
    agent    = load_agent(req.user_id, db)
    song_row = df[df['track_id'] == req.track_id]

    if song_row.empty:
        raise HTTPException(status_code=404, detail="Track not found")

    audio_8 = scaler.transform(song_row[RL_FEATURES])[0]

    # Use original build_context_vector here — feedback is one call, not 200
    vec_12 = build_context_vector(
        audio_8,
        req.user_id,
        req.track_id,
        req.activity,
        db
    )

    agent.update(vec_12, req.reward)
    save_agent(req.user_id, agent, db)

    db.add(ListenHistory(
        user_id    = req.user_id,
        track_id   = req.track_id,
        track_name = req.track_name,
        reward     = req.reward
    ))
    db.commit()

    return {"status": "updated", "reward": req.reward}


# ── Agent stats ────────────────────────────────────────────────────────────
@app.get("/agent-stats/{user_id}")
def agent_stats(user_id: str, db: Session = Depends(get_db)):
    agent = load_agent(user_id, db)
    theta = np.linalg.inv(agent.A) @ agent.b
    audio_prefs = {f: round(float(theta[i]), 4) for i, f in enumerate(RL_FEATURES)}

    context_prefs = {}
    if len(theta) >= 12:
        context_prefs = {
            "time_of_day": round(float(theta[8]),  4),
            "activity":    round(float(theta[9]),  4),
            "skip_rate":   round(float(theta[10]), 4),
            "recency":     round(float(theta[11]), 4),
        }

    return {
        "user_id":             user_id,
        "audio_preferences":   audio_prefs,
        "context_preferences": context_prefs,
        "interpretation": {
            "energy":       "prefers high energy" if audio_prefs['energy']       > 0 else "prefers calm",
            "valence":      "prefers happy songs" if audio_prefs['valence']      > 0 else "prefers sad/dark",
            "danceability": "prefers danceable"   if audio_prefs['danceability'] > 0 else "prefers non-danceable",
            "time_of_day":  "context-aware"       if context_prefs.get('time_of_day', 0) != 0 else "time-agnostic",
        }
    }


# ── Listen history ─────────────────────────────────────────────────────────
@app.get("/history/{user_id}")
def history(user_id: str, db: Session = Depends(get_db)):
    rows = (
        db.query(ListenHistory)
        .filter(ListenHistory.user_id == user_id)
        .order_by(ListenHistory.played_at.desc())
        .limit(20)
        .all()
    )
    return [
        {"track_name": r.track_name,
         "reward":     r.reward,
         "played_at":  r.played_at}
        for r in rows
    ]


# ── Admin dashboard ────────────────────────────────────────────────────────
@app.get("/admin/stats")
def admin_stats(db: Session = Depends(get_db)):
    users = db.query(User).filter(User.username != "admin").all()
    stats = []

    for user in users:
        history = (
            db.query(ListenHistory)
            .filter(ListenHistory.user_id == user.id)
            .order_by(ListenHistory.played_at.asc())
            .all()
        )
        if not history:
            continue

        rewards = [h.reward for h in history]

        rolling = []
        for i in range(len(rewards)):
            w = rewards[max(0, i-4):i+1]
            rolling.append(round(sum(w)/len(w), 3))

        agent = load_agent(user.id, db)
        theta = np.linalg.inv(agent.A) @ agent.b
        audio_prefs = {f: round(float(theta[i]), 4) for i, f in enumerate(RL_FEATURES)}

        context_prefs = {}
        if len(theta) >= 12:
            context_prefs = {
                "time_of_day": round(float(theta[8]),  4),
                "activity":    round(float(theta[9]),  4),
                "skip_rate":   round(float(theta[10]), 4),
                "recency":     round(float(theta[11]), 4),
            }

        stats.append({
            "user_id":           user.id,
            "username":          user.username,
            "total_songs":       len(history),
            "avg_reward":        round(sum(rewards)/len(rewards), 3),
            "rewards_over_time": rolling,
            "reward_breakdown": {
                "completed":  sum(1 for r in rewards if r == 2.0),
                "favourited": sum(1 for r in rewards if r == 3.0),
                "half_skip":  sum(1 for r in rewards if r == 0.5),
                "skipped":    sum(1 for r in rewards if r < 0),
                "removed":    sum(1 for r in rewards if r == -2.0),
            },
            "audio_preferences":   audio_prefs,
            "context_preferences": context_prefs,
            "recent_songs": [
                {"name": h.track_name, "reward": h.reward}
                for h in history[-5:]
            ]
        })

    return {
        "total_users":        len(stats),
        "total_songs_played": sum(s['total_songs'] for s in stats),
        "users":              stats
    }


# ── User has history check ─────────────────────────────────────────────────
@app.get("/user-has-history/{user_id}")
def user_has_history(user_id: str, db: Session = Depends(get_db)):
    count = db.query(ListenHistory).filter(
        ListenHistory.user_id == user_id
    ).count()
    return {"has_history": count > 0, "count": count}


@app.get("/")
def root():
    return {"status": "Music RL API running — 12-dim LinUCB active"}