from locale import currency
from threading import RLock, Condition
from queue import Full, Empty
from typing import Any, Optional, Iterable

from yaml import cyaml

class ThreadSafeArrayDeque:
    """
    线程安全的 ArrayDeque：
    - 环形数组实现，双端操作 O(1)，索引访问 O(1)
    - 可选阻塞行为：block=True/False, timeout=...
    - 若设置 max_capacity：队列满时可选择阻塞等待或抛 Full
      否则自动按 2× 扩容（直到 max_capacity，若为 None 则无限）
    """

    def __init__(self, capacity: int = 8, max_capacity: Optional[int] = None,
                 init: Optional[Iterable[Any]] = None):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if max_capacity is not None and max_capacity < capacity:
            raise ValueError("max_capacity must be >= capacity")

        self._data = [None] * capacity
        self._cap = capacity
        self._max_cap = max_capacity
        self._head = 0     # 指向当前队首元素
        self._tail = 0     # 指向下一个写入位置（队尾后一格）
        self._size = 0

        self._lock = RLock()
        self._not_empty = Condition(self._lock)
        self._not_full  = Condition(self._lock)

        if init:
            for x in init:
                self.append(x, block=False)  # 初始化阶段不阻塞

    # ---------- 基础工具 ----------
    def __len__(self) -> int:
        with self._lock:
            return self._size

    def _index(self, i: int) -> int:
        """将逻辑索引 i (0..size-1，支持负索引) 转为底层数组下标。"""
        n = self._size
        if i < 0:
            i += n
        if not (0 <= i < n):
            raise IndexError(f"index out of range: {i}, size={n}")
        return (self._head + i) % self._cap

    def _grow_if_needed(self):
        """若未达 max_capacity，则按 2× 扩容。"""
        if self._size < self._cap:
            return  # 还有空间，不需要扩容
        new_cap = self._cap * 2
        if self._max_cap is not None:
            new_cap = min(new_cap, self._max_cap)
        if new_cap == self._cap:
            # 达到上限，不能扩容
            return

        old = self._data
        self._data = [None] * new_cap
        # 线性复制到新数组的 0..size-1
        for i in range(self._size):
            self._data[i] = old[(self._head + i) % self._cap]
        self._cap = new_cap
        self._head = 0
        self._tail = self._size

    def _is_full(self) -> bool:
        return self._size == self._cap and (self._max_cap is not None and self._cap == self._max_cap)

    def _push_tail(self, x: Any):
        self._data[self._tail] = x
        self._tail = (self._tail + 1) % self._cap
        self._size += 1

    def _push_head(self, x: Any):
        self._head = (self._head - 1 + self._cap) % self._cap
        self._data[self._head] = x
        self._size += 1

    def _pop_tail(self) -> Any:
        self._tail = (self._tail - 1 + self._cap) % self._cap
        val = self._data[self._tail]
        self._data[self._tail] = None
        self._size -= 1
        return val

    def _pop_head(self) -> Any:
        val = self._data[self._head]
        self._data[self._head] = None
        self._head = (self._head + 1) % self._cap
        self._size -= 1
        return val

    # ---------- 公共 API ----------
    def append(self, item: Any, block: bool = True, timeout: Optional[float] = None):
        """在队尾添加。若达 max_capacity：
           - block=True 则等待空位，支持 timeout；
           - block=False 则抛 Full。
           若未达 max_capacity 则自动扩容（直到上限）。"""
        with self._lock:
            # 先尝试扩容（若可扩）
            if self._size == self._cap and (self._max_cap is None or self._cap < self._max_cap):
                self._grow_if_needed()

            if self._is_full():
                if not block:
                    raise Full
                if not self._not_full.wait(timeout=timeout):
                    raise Full

            # 现在一定有空间
            self._push_tail(item)
            self._not_empty.notify()

    def appendleft(self, item: Any, block: bool = True, timeout: Optional[float] = None):
        with self._lock:
            if self._size == self._cap and (self._max_cap is None or self._cap < self._max_cap):
                self._grow_if_needed()

            if self._is_full():
                if not block:
                    raise Full
                if not self._not_full.wait(timeout=timeout):
                    raise Full

            self._push_head(item)
            self._not_empty.notify()

    def pop(self, block: bool = True, timeout: Optional[float] = None) -> Any:
        """弹出队尾。为空：
           - block=True 则等待，支持 timeout；
           - block=False 则抛 Empty。"""
        with self._lock:
            if self._size == 0:
                if not block:
                    raise Empty
                if not self._not_empty.wait(timeout=timeout):
                    raise Empty
            val = self._pop_tail()
            self._not_full.notify()
            return val

    def popleft(self, block: bool = True, timeout: Optional[float] = None) -> Any:
        with self._lock:
            if self._size == 0:
                if not block:
                    raise Empty
                if not self._not_empty.wait(timeout=timeout):
                    raise Empty
            val = self._pop_head()
            self._not_full.notify()
            return val

    def __getitem__(self, index: int) -> Any:
        """O(1) 索引访问，支持负索引（不弹出）。"""
        with self._lock:
            pos = self._index(index)
            return self._data[pos]

    def clear(self):
        with self._lock:
            self._data = [None] * self._cap
            self._head = self._tail = 0
            self._size = 0
            self._not_full.notify_all()

    def to_list(self) -> list:
        """原子快照（从队首到队尾）。"""
        with self._lock:
            return [self._data[(self._head + i) % self._cap] for i in range(self._size)]

    # 便捷属性
    def is_empty(self) -> bool:
        with self._lock:
            return self._size == 0

    def is_full(self) -> bool:
        with self._lock:
            return self._is_full()

    def capacity(self) -> int:
        with self._lock:
            return self._cap

    def __repr__(self) -> str:
        with self._lock:
            return f"ThreadSafeArrayDeque(size={self._size}/{self._cap}, data={self.to_list()})"



if __name__ == "__main__":
    curent_deque = ThreadSafeArrayDeque(capacity=10, max_capacity=10)
    for i in range(5):
        curent_deque.append(i)
    
    for ele in curent_deque:
        print(ele)
    
    print(curent_deque.to_list())

    curent_deque.appendleft(10)
    print(curent_deque.to_list())
    for ele in curent_deque:
        print(ele)
    

    curent_deque.pop()
    print(curent_deque.to_list())
    for ele in curent_deque:
        print(ele)


    curent_deque.append(11)
    print(curent_deque.to_list())
    for ele in curent_deque:
        print(ele)


    print("check getitem full raise error")
    for i in range(10):
        curent_deque.append(i)

    
    

    