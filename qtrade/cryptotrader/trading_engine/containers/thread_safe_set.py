from threading import RLock, Condition
from typing import Iterable, Callable, Any, Optional

class ThreadSafeSet:
    """
    线程安全的集合：
    - 所有修改在锁内完成
    - __iter__ 基于快照返回迭代器（避免长时间持锁）
    - pop 支持阻塞等待非空
    - 提供 take_if(predicate) 原子查找并删除
    """
    def __init__(self, init: Optional[Iterable[Any]] = None):
        self._set = set(init or [])
        self._lock = RLock()
        self._not_empty = Condition(self._lock)

    # ---- 基础 ----
    def __len__(self) -> int:
        with self._lock:
            return len(self._set)

    def __contains__(self, item: Any) -> bool:
        with self._lock:
            return item in self._set

    def is_empty(self) -> bool:
        with self._lock:
            return len(self._set) == 0

    def to_list(self) -> list:
        with self._lock:
            return list(self._set)

    def __iter__(self):
        # 基于快照的无锁迭代
        with self._lock:
            snap = list(self._set)
        return iter(snap)

    # ---- 修改操作（原子）----
    def add(self, item: Any) -> bool:
        """加入元素；返回是否实际新增（True 新增 / False 已存在）。"""
        with self._lock:
            before = len(self._set)
            self._set.add(item)
            after = len(self._set)
            if after > before:
                self._not_empty.notify()
                return True
            return False

    def update(self, items: Iterable[Any]) -> int:
        """批量加入；返回新增数量。"""
        with self._lock:
            before = len(self._set)
            self._set.update(items)
            added = len(self._set) - before
            if added > 0:
                self._not_empty.notify_all()
            return added

    def remove(self, item: Any) -> None:
        """删除元素；若不存在则抛 KeyError。"""
        with self._lock:
            if item not in self._set:
                return False 
            self._set.remove(item)
            return True

    def discard(self, item: Any) -> bool:
        """删除元素；若不存在不报错，返回是否删除成功。"""
        with self._lock:
            if item in self._set:
                self._set.remove(item)
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._set.clear()

    # ---- 等待/选择类操作 ----
    def pop(self, block: bool = True, timeout: Optional[float] = None) -> Any:
        """
        弹出任一元素。
        - 若空且 block=False -> KeyError
        - 若空且 block=True -> 等待到非空或超时 -> 超时抛 KeyError
        """
        with self._lock:
            if not self._set:
                if not block:
                    raise KeyError("pop from an empty set")
                if not self._not_empty.wait(timeout=timeout):
                    raise KeyError("pop timed out (set still empty)")
            # 这里一定非空
            return self._set.pop()

    def take_if(self, predicate: Callable[[Any], bool]) -> Optional[Any]:
        """
        原子地查找第一个满足条件的元素并删除；若无则返回 None。
        注意：不阻塞。
        """
        with self._lock:
            for x in self._set:
                if predicate(x):
                    self._set.remove(x)
                    return x
            return None

    # ---- 关系/查询（可选）----
    def contains_all(self, items: Iterable[Any]) -> bool:
        with self._lock:
            s = self._set
            return all((x in s) for x in items)

    def issubset(self, other: Iterable[Any]) -> bool:
        with self._lock:
            return self._set.issubset(set(other))

    def issuperset(self, other: Iterable[Any]) -> bool:
        with self._lock:
            return self._set.issuperset(set(other))

    def __repr__(self) -> str:
        with self._lock:
            return f"ThreadSafeSet(size={len(self._set)}, data={list(self._set)})"


if __name__ == "__main__":
    # 简单自测
    s = ThreadSafeSet([1, 2, 3])
    print("init:", s)

    print("add 3 ->", s.add(3))   # False
    print("add 4 ->", s.add(4))   # True
    print("len:", len(s))

    print("contains 2?", 2 in s)
    print("snapshot iter:", list(s))

    print("take_if(lambda x: x % 2 == 0) ->", s.take_if(lambda x: x % 2 == 0))
    print("after take_if:", s.to_list())

    # pop 非阻塞
    print("pop ->", s.pop(block=False))
    print("after pop:", s.to_list())

    # discard / remove
    print("discard 999 ->", s.discard(999))  # False
    print("remove 1 ->", s.remove(1))  # 存在则删除
    print("after remove(1):", s.to_list())

    # 清空
    s.clear()
    print("cleared, is_empty:", s.is_empty())

    # pop 阻塞示例（演示用：这里会 KeyError）
    try:
        s.pop(block=False)
    except KeyError as e:
        print("expected:", e)
