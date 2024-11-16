import threading

class MyThread(threading.Thread):
    def __init__(self, *args, **kwargs):
        super(MyThread, self).__init__(*args, **kwargs)
        self._exception = None

    def run(self):
        try:
            if self._target:
                self._target(*self._args, **self._kwargs)
        except Exception as e:
            print(f'threading exception {self._target}')
            self._exception = e

    def join(self, *args, **kwargs):
        super(MyThread, self).join(*args, **kwargs)
        if self._exception:
            raise self._exception  # Re-raise the exception in the main thread