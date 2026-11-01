"""
In-memory conversation store: one engine Session per session_id.

Temporary: sessions are lost on restart and not shared between workers. PostgreSQL schema `c1`
(sessions, conversation turns) is the planned replacement.
"""
import threading
import time
from collections import OrderedDict

SESSION_TTL_S = 30 * 60     # drop a session after 30 minutes without a message
MAX_SESSIONS = 1000         # and keep at most this many (least recently used go first)


class _Entry:
    __slots__ = ("session", "lock", "last_seen")

    def __init__(self, session):
        self.session = session
        self.lock = threading.Lock()    # one turn at a time per conversation
        self.last_seen = time.monotonic()


class SessionStore:
    def __init__(self, ttl_s=SESSION_TTL_S, max_sessions=MAX_SESSIONS, clock=time.monotonic):
        self.ttl_s = ttl_s
        self.max_sessions = max_sessions
        self.clock = clock
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._lock = threading.Lock()

    def step(self, session_id, new_session, text, bot_text=None):
        """Run one turn in the session's conversation, creating it with new_session() if needed."""
        with self._lock:
            now = self.clock()
            self._expire(now)
            entry = self._entries.get(session_id)
            if entry is None:
                entry = self._entries[session_id] = _Entry(new_session())
                while len(self._entries) > self.max_sessions:
                    self._entries.popitem(last=False)
            entry.last_seen = now
            self._entries.move_to_end(session_id)
        with entry.lock:
            return entry.session.step(text, bot_text=bot_text)

    def _expire(self, now):
        # entries are in last-used order, so stop at the first one still alive
        while self._entries:
            sid, entry = next(iter(self._entries.items()))
            if now - entry.last_seen <= self.ttl_s:
                break
            del self._entries[sid]

    def __len__(self):
        return len(self._entries)

    def __contains__(self, session_id):
        return session_id in self._entries
