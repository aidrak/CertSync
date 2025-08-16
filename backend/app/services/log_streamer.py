import asyncio
from typing import Dict, List, Deque
from collections import deque

class LogStreamer:
    def __init__(self):
        self.subscribers: Dict[str, List[asyncio.Queue]] = {}
        self.history: Dict[str, Deque[str]] = {}
        self.history_max_size = 100

    async def subscribe(self, target: str) -> asyncio.Queue:
        if target not in self.subscribers:
            self.subscribers[target] = []
        
        queue = asyncio.Queue()
        self.subscribers[target].append(queue)
        
        # Send history if it exists
        if target in self.history:
            for msg in self.history[target]:
                await queue.put(msg)
                
        return queue

    def unsubscribe(self, target: str, queue: asyncio.Queue):
        if target in self.subscribers and queue in self.subscribers[target]:
            self.subscribers[target].remove(queue)
            if not self.subscribers[target]:
                del self.subscribers[target]

    async def publish(self, target: str, message: str):
        # Store in history
        if target not in self.history:
            self.history[target] = deque(maxlen=self.history_max_size)
        self.history[target].append(message)

        # Publish to active subscribers
        if target in self.subscribers:
            for queue in self.subscribers[target]:
                await queue.put(message)

    def clear_history(self, target: str):
        if target in self.history:
            del self.history[target]

log_streamer = LogStreamer()
