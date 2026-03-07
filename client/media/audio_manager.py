import pyaudio
import threading

class AudioManager:
    def __init__(self):
        self.p = pyaudio.PyAudio()
import pyaudio
import threading
import queue

class AudioManager:
    def __init__(self):
        self.p = pyaudio.PyAudio()
        self.stream_in = None
        self.stream_out = None
        self.running = False
        self.audio_callback = None
        
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 24000 # Balanced quality/bandwidth
        self.CHUNK = 2048 # Larger chunk = fewer packets = less choppy
        
        self.playback_queue = queue.Queue()

        # Try Input (Microphone)
        try:
            self.stream_in = self.p.open(format=self.FORMAT,
                                         channels=self.CHANNELS,
                                         rate=self.RATE,
                                         input=True,
                                         frames_per_buffer=self.CHUNK)
            print("Audio Input initialized successfully.")
        except Exception as e:
            print(f"Audio Input initialization error: {e}")
            self.stream_in = None

        # Try Output (Speakers)
        try:
            self.stream_out = self.p.open(format=self.FORMAT,
                                          channels=self.CHANNELS,
                                          rate=self.RATE,
                                          output=True)
            print("Audio Output initialized successfully.")
        except Exception as e:
            print(f"Audio Output initialization error: {e}")
            self.stream_out = None
            
        if not self.stream_in and not self.stream_out:
            print("No audio devices available.")
            # Don't set running=False here, allow partial start
            
    def start_audio(self, callback):
        self.audio_callback = callback
        self.running = True
        
        # Start Recording Thread
        if self.stream_in:
            threading.Thread(target=self._record_loop, daemon=True).start()
        else:
            print("Input stream not available, cannot start recording loop.")

        # Start Playback Thread
        if self.stream_out:
            threading.Thread(target=self._playback_loop, daemon=True).start()

    def stop_audio(self):
        self.running = False
        # Give the loop a moment to exit gracefully
        import time
        time.sleep(0.1)
        
        if self.stream_in:
            try:
                self.stream_in.stop_stream()
                self.stream_in.close()
            except Exception as e: print(f"Error closing input stream: {e}")
        if self.stream_out:
            try:
                self.stream_out.stop_stream()
                self.stream_out.close()
            except Exception as e: print(f"Error closing output stream: {e}")
        
        # Clear queue
        with self.playback_queue.mutex:
            self.playback_queue.queue.clear()

    def _record_loop(self):
        print("Audio recording loop started.")
        while self.running and self.stream_in:
            try:
                data = self.stream_in.read(self.CHUNK)
                # print(f"Recorded {len(data)} bytes") # Debug
                if self.audio_callback:
                    self.audio_callback(data)
            except Exception as e:
                print(f"Audio record error: {e}")
                break

    def _playback_loop(self):
        print("Audio playback loop started.")
        while self.running and self.stream_out:
            try:
                data = self.playback_queue.get(timeout=1)
                self.stream_out.write(data)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Audio play error: {e}")
                break

    def play_audio(self, data):
        # Non-blocking put
        if self.running:
            self.playback_queue.put(data)
