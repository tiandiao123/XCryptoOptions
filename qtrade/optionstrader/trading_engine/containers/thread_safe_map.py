#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
from threading import RLock, Condition, Thread
from typing import Any, Optional, Iterable, Mapping, Tuple, Callable, Dict, List

_MISSING = object()

class ThreadSafeMap:
    """
    线程安全字典（Map）。
    - 写操作与读操作都在锁内完成（RLock），保证一致性。
    - items/keys/values/__iter__ 返回的是一次性的快照（list/iter），避免长时间持锁。
    - 提供阻塞等待能力：popitem(block)、wait_for_key(key)、wait_and_pop(key)。
    - 提供原子读改写：compute(key, fn)、compute_if_absent(key, supplier)。
    - 提供删除增强：delete / delete_many / delete_if。

    线程模型：
    - _lock：保护 _map 的互斥锁；
    - _not_empty：当从空->非空时通知（用于等待popitem等）；
    - _changed：任意变更后通知（用于等待某key出现/变化）。
    """

    def __init__(self, init: Optional[Mapping[Any, Any] | Iterable[Tuple[Any, Any]]] = None):
        self._map: Dict[Any, Any] = dict(init or {})
        self._lock = RLock()
        self._not_empty = Condition(self._lock)
        self._changed = Condition(self._lock)

    # ---------- 基础查询 ----------
    def __len__(self) -> int:
        with self._lock:
            return len(self._map)

    def __contains__(self, key: Any) -> bool:
        with self._lock:
            return key in self._map

    def get(self, key: Any, default: Any = None) -> Any:
        with self._lock:
            return self._map.get(key, default)

    def __getitem__(self, key: Any) -> Any:
        with self._lock:
            return self._map[key]

    def to_dict(self) -> dict:
        """获取一致性快照（浅拷贝）。"""
        with self._lock:
            return dict(self._map)

    # ---------- 快照迭代 ----------
    def __iter__(self):
        with self._lock:
            snap = list(self._map.keys())
        return iter(snap)

    def keys(self) -> List[Any]:
        with self._lock:
            return list(self._map.keys())

    def values(self) -> List[Any]:
        with self._lock:
            return list(self._map.values())

    def items(self) -> List[Tuple[Any, Any]]:
        with self._lock:
            return list(self._map.items())

    # ---------- 写/更新 ----------
    def __setitem__(self, key: Any, value: Any) -> None:
        with self._lock:
            was_empty = not self._map
            self._map[key] = value
            if was_empty:
                self._not_empty.notify_all()
            self._changed.notify_all()

    def setdefault(self, key: Any, default: Any = None) -> Any:
        with self._lock:
            if key in self._map:
                return self._map[key]
            was_empty = not self._map
            self._map[key] = default
            if was_empty:
                self._not_empty.notify_all()
            self._changed.notify_all()
            return default

    def update(self, other: Mapping[Any, Any] | Iterable[Tuple[Any, Any]]) -> None:
        with self._lock:
            was_empty = not self._map
            if isinstance(other, Mapping):
                self._map.update(other)
            else:
                for k, v in other:
                    self._map[k] = v
            if was_empty and self._map:
                self._not_empty.notify_all()
            self._changed.notify_all()

    # ---------- 删除 & 弹出 ----------
    def pop(self, key: Any, default: Any = _MISSING) -> Any:
        with self._lock:
            if default is _MISSING:
                val = self._map.pop(key)  # 可能抛 KeyError
            else:
                val = self._map.pop(key, default)
            self._changed.notify_all()
            return val

    def __delitem__(self, key: Any) -> None:
        with self._lock:
            del self._map[key]
            self._changed.notify_all()

    def clear(self) -> None:
        with self._lock:
            if self._map:
                self._map.clear()
                self._changed.notify_all()

    def popitem(self, block: bool = True, timeout: Optional[float] = None) -> Tuple[Any, Any]:
        """
        弹出任意 (key, value)。
        - 空且 block=False：抛 KeyError
        - 空且 block=True：等待非空或超时；超时抛 KeyError
        """
        with self._lock:
            if not self._map:
                if not block:
                    raise KeyError("popitem from empty map")
                if not self._not_empty.wait(timeout=timeout):
                    raise KeyError("popitem timed out (map still empty)")
            item = self._map.popitem()
            self._changed.notify_all()
            return item

    # ---------- 删除增强 ----------
    def delete(self, key: Any) -> bool:
        """
        安全删除单个 key；存在则删除返回 True；不存在返回 False。
        """
        with self._lock:
            if key in self._map:
                del self._map[key]
                self._changed.notify_all()
                return True
            return False

    def delete_many(self, keys: Iterable[Any]) -> int:
        """
        批量删除；返回实际删除的数量。
        """
        with self._lock:
            cnt = 0
            for k in list(keys):
                if k in self._map:
                    del self._map[k]
                    cnt += 1
            if cnt > 0:
                self._changed.notify_all()
            return cnt

    def delete_if(self, predicate: Callable[[Any, Any], bool]) -> int:
        """
        条件删除：对每个 (k, v) 调用 predicate(k, v)，为 True 则删除。
        返回删除数量；遍历使用快照，删除在锁内进行。
        """
        with self._lock:
            to_del = [k for k, v in self._map.items() if predicate(k, v)]
            for k in to_del:
                del self._map[k]
            if to_del:
                self._changed.notify_all()
            return len(to_del)

    # ---------- 原子读改写（RMW） ----------
    def compute(self, key: Any, fn: Callable[[Any | None], Any]) -> Any:
        """
        原子：new = fn(old_or_None)；然后写回并返回 new。
        若 fn 返回 _MISSING，表示“不写回”，仅返回（可用于只读查询）。
        """
        with self._lock:
            old = self._map.get(key, None)
            new = fn(old)
            if new is not _MISSING:
                was_empty = not self._map
                self._map[key] = new
                if was_empty:
                    self._not_empty.notify_all()
                self._changed.notify_all()
            return new

    def compute_if_absent(self, key: Any, supplier: Callable[[], Any]) -> Any:
        """
        若 key 不存在：计算并写入；若存在：直接返回旧值。
        """
        with self._lock:
            if key in self._map:
                return self._map[key]
            was_empty = not self._map
            val = supplier()
            self._map[key] = val
            if was_empty:
                self._not_empty.notify_all()
            self._changed.notify_all()
            return val

    # ---------- 等待类工具 ----------
    def wait_for_key(self, key: Any, timeout: Optional[float] = None) -> Any:
        """
        阻塞直到 key 存在，返回其值；超时抛 TimeoutError。
        """
        with self._lock:
            if key in self._map:
                return self._map[key]
            if not self._changed.wait_for(lambda: key in self._map, timeout=timeout):
                raise TimeoutError(f"wait_for_key timed out: {key!r}")
            return self._map[key]

    def wait_and_pop(self, key: Any, timeout: Optional[float] = None) -> Any:
        """
        阻塞直到 key 存在，然后原子删除该 key 并返回其值；超时抛 TimeoutError。
        """
        with self._lock:
            if key not in self._map:
                if not self._changed.wait_for(lambda: key in self._map, timeout=timeout):
                    raise TimeoutError(f"wait_and_pop timed out: {key!r}")
            val = self._map.pop(key)
            self._changed.notify_all()
            return val

    def __repr__(self) -> str:
        with self._lock:
            return f"ThreadSafeMap(size={len(self._map)}, data={dict(self._map)})"


# ------------------- 自测示例 -------------------
if __name__ == "__main__":
    m = ThreadSafeMap({"a": 1})
    print("init:", m)

    # 基础写读
    m["b"] = 2
    m.update({"c": 3, "d": 4})
    print("items snapshot:", m.items())

    # 原子RMW
    m.compute("a", lambda old: (old or 0) + 10)     # a -> 11
    v = m.compute_if_absent("e", lambda: 99)        # e -> 99
    print("after compute & compute_if_absent:", m.to_dict(), "; e=", v)

    # 删除增强
    print("delete('d'):", m.delete("d"))            # True
    print("delete('zzz'):", m.delete("zzz"))        # False
    print("delete_many(['a','x','c']):", m.delete_many(["a", "x", "c"]))  # 2
    print("after deletes:", m.to_dict())

    removed = m.delete_if(lambda k, v: isinstance(v, int) and v % 2 == 1)
    print("delete_if(odd values) ->", removed)
    print("after delete_if:", m.to_dict())

    # popitem 非阻塞
    try:
        kv = m.popitem(block=False)
        print("popitem(non-block):", kv)
    except KeyError as e:
        print("popitem(non-block) KeyError:", e)

    # wait_for_key / wait_and_pop 演示（多线程）
    def producer():
        import time
        time.sleep(0.2)
        m["token"] = "abc"
        print("[producer] set token=abc")

    t = Thread(target=producer, daemon=True)
    t.start()

    try:
        val = m.wait_for_key("token", timeout=1.0)
        print("wait_for_key('token') ->", val)
        val2 = m.wait_and_pop("token", timeout=1.0)
        print("wait_and_pop('token') ->", val2)
    except TimeoutError as e:
        print("Timeout:", e)

    print("final:", m.to_dict())
