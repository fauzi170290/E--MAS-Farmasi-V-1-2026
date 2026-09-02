"""OS lock released on crash; prevents two workers/processes screening one inbox."""
import os


class MonitorProcessLock:
    def __init__(self, path):
        self.path = path
        self.handle = None

    def acquire(self):
        self.handle = self.path.open('a+b')
        self.handle.seek(0, 2)
        if not self.handle.tell():
            self.handle.write(b'0')
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            self.handle = None
            return False
        return True

    def release(self):
        if self.handle is not None:
            self.handle.close()
            self.handle = None
