import numpy as np
import json
from sqlalchemy.orm import Session
from models import AgentState


class LinUCBAgent:
    def __init__(self, n_features=12, alpha=0.3):
        self.alpha = alpha
        self.n     = n_features
        self.A     = np.identity(n_features)   # (12, 12)
        self.b     = np.zeros(n_features)      # (12,)

    def select(self, candidates: np.ndarray) -> int:
        """candidates: shape (pool_size, 12) — returns index of best song"""
        A_inv  = np.linalg.inv(self.A)
        theta  = A_inv @ self.b
        scores = []
        for x in candidates:
            exploit = theta @ x
            explore = self.alpha * np.sqrt(x @ A_inv @ x)
            scores.append(exploit + explore)
        return int(np.argmax(scores))

    def update(self, x: np.ndarray, reward: float):
        """x: 12-dim vector, reward: float"""
        self.A += np.outer(x, x)
        self.b += reward * x


def load_agent(user_id: str, db: Session) -> LinUCBAgent:
    """Load agent from DB (A_matrix + b_vector as JSON). Fresh agent if new user."""
    row = db.query(AgentState).filter(AgentState.user_id == user_id).first()
    if row:
        agent   = LinUCBAgent(n_features=12, alpha=0.3)
        agent.A = np.array(json.loads(row.A_matrix))
        agent.b = np.array(json.loads(row.b_vector))
        return agent
    return LinUCBAgent(n_features=12, alpha=0.3)   # brand new user


# def save_agent(user_id: str, agent: LinUCBAgent, db: Session):
#     """Upsert A_matrix and b_vector as JSON text into DB."""
#     A_json = json.dumps(agent.A.tolist())
#     b_json = json.dumps(agent.b.tolist())
#     row    = db.query(AgentState).filter(AgentState.user_id == user_id).first()
#     if row:
#         row.A_matrix = A_json
#         row.b_vector = b_json
#     else:
#         db.add(AgentState(
#             user_id  = user_id,
#             A_matrix = A_json,
#             b_vector = b_json
#         ))
#     db.commit()

def save_agent(user_id: str, agent: LinUCBAgent, db: Session):
    try:
        A_json = json.dumps(agent.A.tolist())
        b_json = json.dumps(agent.b.tolist())
        row = db.query(AgentState).filter(AgentState.user_id == user_id).first()
        if row:
            row.A_matrix = A_json
            row.b_vector = b_json
        else:
            db.add(AgentState(user_id=user_id, A_matrix=A_json, b_vector=b_json))
        db.commit()
        print(f"Agent saved for {user_id}, b_norm={float(sum(x**2 for x in agent.b)**0.5):.4f}")
    except Exception as e:
        print(f"save_agent ERROR: {e}")
        db.rollback()