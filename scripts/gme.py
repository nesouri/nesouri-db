from ctypes import *

lib = cdll.LoadLibrary("libgme.so")

class Music_Emu(Structure):
    pass

class GmeError(Exception):
    pass

class GmeBuffer(object):
    def __init__(self, rate, seconds):
        self.buf = (c_short * (2 * rate * seconds))()

    def clear(self):
        memset(addressof(self.buf), 0, sizeof(self.buf))

    def get_buffer(self):
        return self.buf

    def get_size(self):
        return len(self.buf)

    def get_bytes(self, trim=False):
        ret = bytes(self.buf)
        if not trim:
            return ret

        position = 0
        for x in range(len(ret) - 4, -1, -4):
            if ret[x] == 0 and ret[x + 1] == 0 and ret[x + 2] == 0 and ret[x + 3] == 0:
                position = x
            else:
                break

        return ret[:position - 4]

class Gme(object):
    @staticmethod
    def from_file(path, rate):
        open_file = lib.gme_open_file
        open_file.argtypes = [c_char_p, POINTER(POINTER(Music_Emu)), c_int]
        emu = POINTER(Music_Emu)()
        err = open_file(c_char_p(path.encode("utf-8")), byref(emu), int(rate))
        if err != 0:
            raise GmeError("Could not open file: " + path)
        return Gme(emu, rate)

    def __init__(self, emu, rate):
        self.emu = emu
        self.rate = rate

    def create_buffer(self, seconds=10):
        return GmeBuffer(self.rate, seconds)

    def track_count(self):
        return lib.gme_track_count(self.emu)

    def start_track(self, track):
        err = lib.gme_start_track(self.emu, track)
        if err != 0:
            raise GmeError("Could not start track: %d" % track)

    def play(self, buf):
        err = lib.gme_play(self.emu, buf.get_size(), buf.get_buffer())
        if err != 0:
            raise GmeError("Could not decode")

    def track_ended(self):
        return lib.gme_track_ended(self.emu) == 1

    def set_stereo_depth(self, depth):
        lib.gme_set_stereo_depth(self.emu, c_double(depth))

    def close(self):
        lib.gme_delete(self.emu)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
