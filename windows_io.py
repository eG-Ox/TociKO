"""Ventana del cliente oficial, entrada relativa y captura de mouse Raw Input."""
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
import threading

user = C.WinDLL('user32', use_last_error=True)
kernel = C.WinDLL('kernel32', use_last_error=True)
user.GetForegroundWindow.restype = W.HWND
user.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
kernel.OpenProcess.restype = W.HANDLE
kernel.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
kernel.CloseHandle.argtypes = [W.HANDLE]
user.GetClientRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
user.ClientToScreen.argtypes = [W.HWND, C.POINTER(W.POINT)]


def game_region():
    hwnd = user.GetForegroundWindow()
    pid = W.DWORD()
    user.GetWindowThreadProcessId(hwnd, C.byref(pid))
    process = kernel.OpenProcess(0x1000, False, pid.value)
    if not process:
        return None
    try:
        size, path = W.DWORD(32768), C.create_unicode_buffer(32768)
        if not kernel.QueryFullProcessImageNameW(process, 0, path, C.byref(size)):
            return None
        if Path(path.value).name.lower() != 'robloxplayerbeta.exe':
            return None
    finally:
        kernel.CloseHandle(process)
    rect, origin = W.RECT(), W.POINT(0, 0)
    if not user.GetClientRect(hwnd, C.byref(rect)) or not user.ClientToScreen(hwnd, C.byref(origin)):
        return None
    if rect.right <= 0 or rect.bottom <= 0:
        return None
    return {'left': origin.x, 'top': origin.y, 'width': rect.right, 'height': rect.bottom}


def focused():
    return game_region() is not None


def dpi_aware():
    try:
        user.SetProcessDpiAwarenessContext.argtypes = [W.HANDLE]
        user.SetProcessDpiAwarenessContext(C.c_void_p(-4))
    except AttributeError:
        user.SetProcessDPIAware()


class MouseInput(C.Structure):
    _fields_ = [('dx', W.LONG), ('dy', W.LONG), ('mouseData', W.DWORD),
                ('dwFlags', W.DWORD), ('time', W.DWORD), ('dwExtraInfo', C.c_size_t)]


class KeyInput(C.Structure):
    _fields_ = [('wVk', W.WORD), ('wScan', W.WORD), ('dwFlags', W.DWORD),
                ('time', W.DWORD), ('dwExtraInfo', C.c_size_t)]


class InputUnion(C.Union):
    _fields_ = [('mi', MouseInput), ('ki', KeyInput)]


class Input(C.Structure):
    _anonymous_ = ('payload',)
    _fields_ = [('type', W.DWORD), ('payload', InputUnion)]


user.SendInput.argtypes = [W.UINT, C.POINTER(Input), C.c_int]
user.SendInput.restype = W.UINT


class Driver:
    def __init__(self):
        from pynput import keyboard, mouse
        self.keyboard, self.mouse = keyboard.Controller(), mouse.Controller()
        self.special = {'space': keyboard.Key.space, 'shift': keyboard.Key.shift}
        self.buttons = {'left': mouse.Button.left, 'right': mouse.Button.right}

    def press(self, key):
        if key in self.buttons:
            self.mouse.press(self.buttons[key])
        else:
            self.keyboard.press(self.special.get(key, key))

    def release(self, key):
        if key in self.buttons:
            self.mouse.release(self.buttons[key])
        else:
            self.keyboard.release(self.special.get(key, key))

    def move(self, dx, dy):
        if not dx and not dy:
            return
        event = Input(type=0, mi=MouseInput(dx=dx, dy=dy, dwFlags=1))
        if user.SendInput(1, C.byref(event), C.sizeof(Input)) != 1:
            raise C.WinError(C.get_last_error())


# RAWMOUSE tiene un union de 4 bytes alineado a DWORD, seguido de otros 4 campos.
class RawHeader(C.Structure):
    _fields_ = [('type', W.DWORD), ('size', W.DWORD), ('device', W.HANDLE), ('wparam', W.WPARAM)]


class RawMouseData(C.Structure):
    _fields_ = [('flags', W.USHORT), ('buttons', W.ULONG), ('raw_buttons', W.ULONG),
                ('x', W.LONG), ('y', W.LONG), ('extra', W.ULONG)]


class RawInput(C.Structure):
    _fields_ = [('header', RawHeader), ('mouse', RawMouseData)]


class RawDevice(C.Structure):
    _fields_ = [('page', W.USHORT), ('usage', W.USHORT), ('flags', W.DWORD), ('target', W.HWND)]


WNDPROC = C.WINFUNCTYPE(C.c_ssize_t, W.HWND, W.UINT, W.WPARAM, W.LPARAM)


class WindowClass(C.Structure):
    _fields_ = [('style', W.UINT), ('proc', WNDPROC), ('class_extra', C.c_int),
                ('window_extra', C.c_int), ('instance', W.HINSTANCE), ('icon', W.HICON),
                ('cursor', W.HANDLE), ('background', W.HBRUSH), ('menu', W.LPCWSTR), ('name', W.LPCWSTR)]


class RawMouse:
    def __init__(self):
        self.lock = threading.Lock()
        self.delta = [0, 0]
        self.ready = threading.Event()
        self.error, self.hwnd = None, None

    def take(self):
        with self.lock:
            delta, self.delta = self.delta, [0, 0]
            return delta

    def _run(self):
        user.DefWindowProcW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
        user.DefWindowProcW.restype = C.c_ssize_t
        user.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD,
                                        C.c_int, C.c_int, C.c_int, C.c_int, W.HWND, W.HMENU, W.HINSTANCE, C.c_void_p]
        user.CreateWindowExW.restype = W.HWND
        user.GetRawInputData.argtypes = [W.HANDLE, W.UINT, C.c_void_p, C.POINTER(W.UINT), W.UINT]
        user.GetRawInputData.restype = W.UINT
        user.RegisterRawInputDevices.argtypes = [C.POINTER(RawDevice), W.UINT, W.UINT]
        user.RegisterClassW.argtypes = [C.POINTER(WindowClass)]
        user.GetMessageW.argtypes = [C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT]
        user.TranslateMessage.argtypes = [C.POINTER(W.MSG)]
        user.DispatchMessageW.argtypes = [C.POINTER(W.MSG)]
        user.DispatchMessageW.restype = C.c_ssize_t
        user.DestroyWindow.argtypes = [W.HWND]
        user.IsWindow.argtypes = [W.HWND]
        user.UnregisterClassW.argtypes = [W.LPCWSTR, W.HINSTANCE]
        kernel.GetModuleHandleW.restype = W.HMODULE
        kernel.GetModuleHandleW.argtypes = [W.LPCWSTR]
        instance = kernel.GetModuleHandleW(None)
        name = f'RbxBotRawMouse_{id(self)}'

        @WNDPROC
        def callback(hwnd, message, wparam, lparam):
            try:
                if message == 0x00FF:  # WM_INPUT
                    size = W.UINT()
                    user.GetRawInputData(W.HANDLE(lparam), 0x10000003, None, C.byref(size), C.sizeof(RawHeader))
                    buffer = C.create_string_buffer(size.value)
                    count = user.GetRawInputData(W.HANDLE(lparam), 0x10000003, buffer, C.byref(size), C.sizeof(RawHeader))
                    if count != 0xFFFFFFFF and count >= C.sizeof(RawInput):
                        raw = C.cast(buffer, C.POINTER(RawInput)).contents
                        if raw.header.type == 0 and not raw.mouse.flags & 1:
                            with self.lock:
                                self.delta[0] += raw.mouse.x
                                self.delta[1] += raw.mouse.y
                if message == 0x0010:  # WM_CLOSE
                    user.DestroyWindow(hwnd)
                    return 0
                if message == 0x0002:
                    user.PostQuitMessage(0)
                    return 0
            except Exception as exc:
                self.error = exc
            return user.DefWindowProcW(hwnd, message, wparam, lparam)

        cls = WindowClass(proc=callback, instance=instance, name=name)
        registered = False
        try:
            if not user.RegisterClassW(C.byref(cls)):
                raise C.WinError(C.get_last_error())
            registered = True
            self.hwnd = user.CreateWindowExW(0, name, name, 0, 0, 0, 0, 0, W.HWND(-3), None, instance, None)
            if not self.hwnd:
                raise C.WinError(C.get_last_error())
            device = RawDevice(1, 2, 0x100, self.hwnd)  # RIDEV_INPUTSINK
            if not user.RegisterRawInputDevices(C.byref(device), 1, C.sizeof(device)):
                raise C.WinError(C.get_last_error())
            self.ready.set()
            msg = W.MSG()
            while user.GetMessageW(C.byref(msg), None, 0, 0) > 0:
                user.TranslateMessage(C.byref(msg))
                user.DispatchMessageW(C.byref(msg))
        except Exception as exc:
            self.error = exc
            self.ready.set()
        finally:
            if self.hwnd and user.IsWindow(self.hwnd):
                user.DestroyWindow(self.hwnd)
            if registered:
                user.UnregisterClassW(name, instance)

    def __enter__(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        if not self.ready.wait(5):
            raise RuntimeError('No se pudo iniciar Raw Input.')
        if self.error:
            raise self.error
        return self

    def __exit__(self, *exc):
        user.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
        if self.hwnd:
            user.PostMessageW(self.hwnd, 0x0010, 0, 0)
        self.thread.join(timeout=5)
