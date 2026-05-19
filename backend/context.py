import numpy as np
from datetime import datetime
from sqlalchemy.orm import Session
from models import ListenHistory


def build_context_vector(
    audio_8:  np.ndarray,   # 8-dim scaled audio features
    user_id:  str,
    track_id: str,          # to check recency
    activity: float,        # 0.0=relaxing, 0.5=working, 1.0=exercising
    db:       Session
) -> np.ndarray:
    """
    Builds 12-dim vector = 8 audio + 4 context.
    Mirrors notebook's build_context_vector exactly.

    context[0] time_norm  → real system clock  (0–1)
    context[1] activity   → from frontend      (0.0 / 0.5 / 1.0)
    context[2] skip_rate  → from DB history    (0–1)
    context[3] recency    → played in last 20? (0 or 1)
    """

    # 1. time of day — real system clock
    time_norm = datetime.now().hour / 24.0

    # 2. activity — validated, default to 0.5 (working) if invalid
    act = float(activity) if activity in [0.0, 0.5, 1.0] else 0.5

    # 3. skip_rate + 4. recency — from real DB history
    history = (
        db.query(ListenHistory)
        .filter(ListenHistory.user_id == user_id)
        .order_by(ListenHistory.played_at.desc())
        .limit(20)
        .all()
    )

    if history:
        skips            = sum(1 for h in history if h.reward < 0)
        skip_rate        = skips / len(history)
        recent_track_ids = {h.track_id for h in history}
    else:
        skip_rate        = 0.0
        recent_track_ids = set()

    recency = 1.0 if track_id in recent_track_ids else 0.0

    context_4 = np.array([time_norm, act, skip_rate, recency])

    return np.concatenate([audio_8, context_4])   # (12,)


def build_pool_12(
    pool_audio:  np.ndarray,   # (pool_size, 8)
    pool_idxs:   np.ndarray,   # indices into df/song_matrix
    df,                        # original dataframe to get track_ids
    user_id:     str,
    activity:    float,
    db:          Session
) -> np.ndarray:
    """
    Builds full (pool_size, 12) matrix for agent.select().
    Calls build_context_vector once per candidate song.
    """
    pool_12 = []
    for i, audio_8 in enumerate(pool_audio):
        track_id = df.iloc[pool_idxs[i]]['track_id']
        vec_12   = build_context_vector(audio_8, user_id, track_id, activity, db)
        pool_12.append(vec_12)
    return np.array(pool_12)   # (pool_size, 12)