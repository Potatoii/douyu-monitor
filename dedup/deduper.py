from collections import OrderedDict


class Deduper:
    """跨端口去重: 以消息 ID 为键, FIFO 容量限制."""

    def __init__(self, max_size: int = 200_000):
        if max_size < 1:
            raise ValueError("max_size must be >= 1")
        self.max_size = max_size
        self._seen: OrderedDict[str, None] = OrderedDict()

    def is_new(self, message_id: str) -> bool:
        if message_id in self._seen:
            return False
        self._seen[message_id] = None
        if len(self._seen) > self.max_size:
            self._seen.popitem(last=False)
        return True

    def __len__(self) -> int:
        return len(self._seen)
