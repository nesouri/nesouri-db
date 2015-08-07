from ctypes import *

lib = cdll.LoadLibrary("libgme.so")

class Music_Emu(Structure):
    pass

class GmeError(Exception):
    pass

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
        return (c_short * (2 * self.rate * seconds))()

    def track_count(self):
        return lib.gme_track_count(self.emu)

    def start_track(self, track):
        err = lib.gme_start_track(self.emu, track)
        if err != 0:
            raise GmeError("Could not start track: %d" % track)

    def play(self, buf):
        err = lib.gme_play(self.emu, len(buf), buf)
        if err != 0:
            raise GmeError("Could not decode")

    def track_ended(self):
        return lib.gme_track_ended(self.emu) == 1
